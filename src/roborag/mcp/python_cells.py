"""Opt-in episode Python cells. Only an explicit public RPC can reach the robot.

Worker isolation is enforced by bwrap, not Python introspection filters. No repo,
TRAIN files, native config, credentials, host network or simulator handles are
mounted. The existing evidence tools remain the only TRAIN access path.
"""
import asyncio
import base64
import json
from pathlib import Path
import time
from typing import Annotated, Literal

from pydantic import Field

from mcp.types import CallToolResult, ImageContent, TextContent

ROOT = Path(__file__).resolve().parents[3]


class PythonCells:
    def __init__(self, server, memory):
        self.server, self.memory = server, memory
        self.process = None
        self.lock = asyncio.Lock()
        self.index = 0

    async def start(self):
        extension = {'hang_mugs': 'hang_worker.py', 'sweep_blocks': 'sweep_worker.py',
                     'pack_objects_into_box': 'pack_worker.py'}.get(self.memory.task)
        worker = Path(__file__).with_name(extension or 'python_worker.py')
        command = ['/usr/bin/bwrap', '--die-with-parent', '--unshare-all', '--new-session',
                   '--ro-bind', '/usr', '/usr', '--ro-bind', '/lib', '/lib',
                   '--ro-bind', '/lib64', '/lib64', '--symlink', 'usr/bin', '/bin',
                   '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp',
                   '--ro-bind', str(worker), '/worker.py',
                   *(['--ro-bind', str(Path(__file__).with_name('python_worker.py')), '/base_worker.py'] if extension else []),
                   '--ro-bind', str((ROOT/'data/hexashell-agent-python').resolve()), '/packages',
                   '--clearenv', '--setenv', 'PATH', '/usr/bin:/bin',
                   '--setenv', 'PYTHONPATH', '/packages', '--setenv', 'OPENBLAS_NUM_THREADS', '1',
                   '--chdir', '/tmp', '--', '/usr/bin/python3', '-u', '/worker.py']
        self.process = await asyncio.create_subprocess_exec(*command, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, limit=8*1024*1024)

    async def close(self):
        if self.process is not None:
            if self.process.returncode is None:
                self.process.kill()
            await self.process.wait()
            self.process = None

    async def dispatch(self, method, arguments, reference_content=None):
        if method == 'state':
            if arguments:
                raise ValueError('state takes no arguments')
            return self.memory.state()
        if method == 'image':
            camera = arguments.get('camera')
            if camera not in ('head', 'wrist_l', 'wrist_r'):
                raise ValueError('Unknown camera')
            return base64.b64encode((self.memory.workspace/f'obs/{camera}.png').read_bytes()).decode()
        if method == 'hold':
            result = await self.server.call_tool('hold_joints', arguments)
            if result.is_error:
                raise RuntimeError(str(result.content))
            return json.loads(result.content[0].text)
        if method == 'measure' and self.memory.task == 'hang_mugs':
            result = await self.server.call_tool('measure_mug_geometry', arguments)
            if result.is_error:
                raise RuntimeError(str(result.content))
            return json.loads(result.content[0].text)
        if (self.memory.task == 'pack_objects_into_box' and not self.memory.no_rag
                and method in ('inspect_transfer_reference', 'match_scene_reference', 'prepare_motion_transfer')):
            result = await self.server.call_tool(method, arguments)
            if result.is_error:
                raise RuntimeError(str(result.content))
            # Keep TRAIN/current labels and images attached to the cell response.
            # Only the tool's public JSON enters the persistent worker namespace.
            if reference_content is not None:
                reference_content.extend(result.content[1:])
            return json.loads(result.content[0].text)
        if method == 'execute':
            # This calls the SAME tool validation, plan gate, lock, compiler and
            # simulator submit used for regular actions. No private submit RPC.
            result = await self.server.call_tool('execute_chunk', arguments)
            if result.is_error:
                raise RuntimeError(str(result.content))
            return json.loads(result.content[0].text)
        raise ValueError('Unknown public method')

    async def run(self, code, cameras, timeout=120):
        async with self.lock:
            self.index += 1
            before = self.memory.state()['step']
            fresh = self.process is None or self.process.returncode is not None
            if fresh:
                await self.start()
            self.memory.audit('python_cell_start', dict(cell=self.index, code=code), dict(step=before, new_namespace=fresh))
            images, calls, stopped = [], [], False
            reference_content = []
            deadline = time.monotonic() + timeout
            result = {}
            try:
                self.process.stdin.write((json.dumps(dict(code=code))+'\n').encode())
                await self.process.stdin.drain()
                while True:
                    line = await asyncio.wait_for(self.process.stdout.readline(), max(.01, deadline-time.monotonic()))
                    if not line:
                        raise RuntimeError('Python worker exited; namespace lost')
                    item = json.loads(line)
                    if item['kind'] == 'done':
                        result = item
                        break
                    if item['kind'] == 'display':
                        if len(images) < 6:
                            images.append(ImageContent(type='image', mime_type='image/png', data=item['data']))
                        continue
                    if item['kind'] != 'call':
                        raise ValueError('Invalid worker protocol')
                    method, arguments = item['method'], item['arguments']
                    try:
                        if method in ('execute', 'hold') and stopped:
                            raise RuntimeError('Motion stopped in this cell. Inspect feedback and revise in a new cell.')
                        value = await self.dispatch(method, arguments, reference_content)
                        if method in ('execute', 'hold'):
                            receipt = value.get('execution', {})
                            calls.append(receipt)
                            stopped = bool(receipt.get('discarded_rows') or receipt.get('rejection') or receipt.get('episode_over') or
                                           max((receipt.get('last_tracking') or {}).get('tracking_error_m', {}).values(), default=0) > .04 or
                                           value.get('current_observation', {}).get('episode_over'))
                        reply = dict(value=value)
                    except Exception as exc:
                        if method in ('execute', 'hold'):
                            stopped = True
                        reply = dict(error=f'{type(exc).__name__}: {exc}')
                    self.process.stdin.write((json.dumps(reply)+'\n').encode())
                    await self.process.stdin.drain()
            except (Exception, asyncio.CancelledError) as exc:
                await self.close()
                result = dict(error=f'{type(exc).__name__}: {exc}', namespace_lost=True,
                              note='Executed actions remain executed; never replay the cell blindly.')
                if isinstance(exc, asyncio.CancelledError):
                    self.memory.audit('python_cell_cancelled', dict(cell=self.index), result)
                    raise
            after = self.memory.state()['step']
            result.update(cell=self.index, new_namespace=fresh, step_before=before, step_after=after,
                          action_steps=after-before, motions=calls, motion_stopped=stopped)
            result.pop('kind', None)
            self.memory.audit('python_cell', dict(cell=self.index, code=code), result)
            observation = self.memory.observation(cameras)
            return CallToolResult(content=[TextContent(type='text', text=json.dumps(result)),
                                          *reference_content, *images, *observation.content])


def register_tools(server, memory, read_only):
    kernel = PythonCells(server, memory)

    @server.tool()
    async def hold_joints(steps: Annotated[int, Field(ge=1, le=24, strict=True)], subgoal: str, arm: Literal['left','right'] | None = None,
                          gripper: float | None = None) -> CallToolResult:
        """Hold both MEASURED arm joint positions for 1-24 native steps, optionally changing one gripper.

        No Cartesian IK, object sensing or grasp guarantee. Omit arm/gripper to
        settle with both commands preserved. Inspect RGB after closing/releasing.
        Each dispatch counts toward the native budget. A plan is required.
        """
        from mcp.server.mcpserver.exceptions import ToolError
        from roborag.toast_motion import validate_joint_hold
        request = dict(steps=steps, arm=arm, gripper=gripper)
        try:
            validate_joint_hold(request)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        if memory.plan is None:
            raise ToolError('record_plan must precede execution')
        async with memory.lock:
            if memory.state()['episode_over']:
                return memory.observation([])
            command = dict(joint_hold=request, subgoal=subgoal)
            receipt = await memory.submit(command)
            memory.audit('hold_joints', command, receipt)
            return memory.observation([], receipt=receipt['result'])

    async def python_cell(code: str, cameras: list[Literal['head', 'wrist_l', 'wrist_r']] = ['head', 'wrist_r']) -> CallToolResult:
        """Persistent Python: variables/functions/imports survive cells; stdout, last value, errors and fresh RGB/state return.

        np, math, Rotation, Image, display(image), robo are defined. Pure computation
        is isolated from host/network/simulator; no hidden object or reward state.
        robo.state() includes current camera K,T and action_state; robo.image(camera)
        returns PIL RGB; robo.show(camera) displays it. Save snapshots with images.
        pixel_to_plane(snapshot,camera,[u,v],z) uses YOUR height assumption.
        triangulate([(snapshot,camera,[u,v]),...]) returns xyz and reprojection error
        for the same STATIC visible point; matching features remains your decision.
        tcp_pose(snapshot,arm) -> (xyz, scipy Rotation); quaternion convention wxyz.
        The same pure geometry helpers also accept the robo. prefix, with identical
        arguments: robo.pixel_to_plane(...), robo.triangulate(...), robo.tcp_pose(...).

        robo.move(arm,xyz=None,quaternion=None,gripper=None,steps=16,subgoal=...,
        expected_feedback=...) requests 1-24 straight TCP samples with interpolated
        orientation. xyz=None holds current TCP while turning. Omitted gripper holds
        its command. Original native IK/limits/step budget apply; no grasp planner.
        robo.grip(arm,value,steps=8) holds measured arm JOINTS while changing one gripper,
        bypassing Cartesian IK. robo.hold(steps=8) holds both joints/gripper commands.
        Values are COMMANDS, not holding sensors; inspect RGB after contact.
        robo.execute(subgoal=...,expected_feedback=...,actions/segments/targets=...)
        wraps execute_chunk; robo.home() wraps return_home after you withdraw clear.
        A move returns execution and current_observation plus pose target_error.
        IK rejection, truncation or >4cm last-row tracking error stops further motion
        in this cell. Rejected rows consume no steps and change neither gripper.
        The native IK continuity limit is 0.25rad per joint; revise the approach
        or use smaller increments from the latest measured pose. Read RGB and revise in a NEW
        cell. End cells at uncertain contacts, grasp/lift and release; combine
        predictable free motion/calculations in functions. Do not treat pose error
        as grasp success. 120-second compute deadline; completed motions persist
        after errors, so never blindly rerun a failed cell. record_plan still precedes movement.
        """
        return await kernel.run(code, cameras)
    if memory.task == 'hang_mugs':
        python_cell.__doc__ += '''

        Hang-mug helpers: robo.measure(command, **arguments) calls the optional
        measure_mug_geometry tool with the same arguments and zero action steps.
        robo.move_feature(arm,source,target,quaternion=None,gripper=None,steps=16,
        subgoal=...,expected_feedback=...) moves a chosen CURRENT world feature
        along a line while rotating. source/target are world xyz, quaternion is wxyz.
        It accounts for the feature offset from TCP at every intermediate sample;
        target=source rotates about the selected feature. This assumes rigid grasp,
        not collision-free motion or observed feature tracking. Read RGB after contact.
        It shares execute_chunk validation, 1-24-row dispatches, plan requirement,
        native step budget and stop-on-truncation with robo.move.
        '''
    if memory.task == 'sweep_blocks':
        python_cell.__doc__ += '''

        Held-feature helpers: robo.move_feature(arm,source,target,quaternion=None,
        gripper=None,steps=16,subgoal=...,expected_feedback=...) moves one chosen
        CURRENT visible world point along a line while compensating for rotation.
        robo.move_features(features,steps=16,subgoal=...,expected_feedback=...)
        accepts {"left":{"source":[x,y,z],"target":[x,y,z],"quaternion":[w,x,y,z]},
                 "right":{"source":[x,y,z],"target":[x,y,z]}}; either arm may be
        omitted. Both requested feature paths share one 1-24-row native dispatch,
        not two sequential arm moves. Quaternion and gripper command are optional.
        Select your own visible points, for example a held tool tip or pan lip.
        target=source rotates around that point; it does NOT pin a physical object.
        Predictions use measured robot state plus an assumed fixed grasp offset.
        They do not track objects, detect grasp, prevent collisions or certify success.
        Remeasure after slip, handover, release or contact; do not reuse stale offsets.
        Use short contact strokes, inspect RGB and revise. No sweeping path, grasp,
        object count, task stage, scene coordinates or native reward is supplied.
        '''
    if memory.task == 'pack_objects_into_box' and not memory.no_rag:
        python_cell.__doc__ += '''

        Calibrated TRAIN references also work inside persistent cells:
        robo.inspect_reference(source,frames,cameras=['head'],measure_support=False),
        robo.match_reference(source,reference_frame,label,landmarks,mode='planar',max_error_m=.02),
        robo.prepare_reference(source,start_frame,end_frame,arm,knots,source_arm=None).
        Arguments match inspect_transfer_reference, match_scene_reference and
        prepare_motion_transfer exactly. These calls consume zero control steps;
        their JSON values can be saved in Python and their labelled TRAIN/current
        images are attached to the cell response. Retrieve the source first.
        End a cell after inspecting images or matching uncertain correspondences.
        A prepare result has entry_target, first_target, final_target, path_samples;
        each target contains tcp_xyz, quaternion_wxyz and historical gripper.
        You can pass its xyz/quaternion to robo.move, choosing CURRENT grip and
        steps yourself. No reference is executed automatically and no task stage
        is enforced. Remeasure an object or destination after it moves; anchors
        record measured_at_step and do not track moving objects.
        '''
    server.tool()(python_cell)
    return kernel
