"""Run with the registered simulator's Python. Reset one scene and save a real image."""
import argparse
import json
import os
from pathlib import Path
import sys


def libero(root, out, args):
    import yaml
    folder = root / 'libero/libero'
    # LIBERO otherwise prompts for global configuration on first import.
    config = out / 'libero-config'
    config.mkdir()
    os.environ['LIBERO_CONFIG_PATH'] = str(config)
    (config/'config.yaml').write_text(yaml.safe_dump({k:str(p) for k,p in {
        'benchmark_root':folder, 'bddl_files':folder/'bddl_files', 'init_states':folder/'init_files',
        'datasets':root/'datasets', 'assets':folder/'assets'}.items()}))
    from libero.libero import benchmark
    from libero.libero.envs import OffScreenRenderEnv
    suite_name = args.suite or ('libero_spatial_with_mug' if args.adapter=='libero-pro' else 'libero_spatial')
    suite = benchmark.get_benchmark_dict()[suite_name]()
    task = args.task or '0'
    index = int(task) if task.isdigit() else suite.get_task_names().index(task)
    if not 0 <= index < suite.n_tasks:
        raise ValueError('Task index outside suite')
    env = OffScreenRenderEnv(bddl_file_name=suite.get_task_bddl_file_path(index), camera_heights=128, camera_widths=128)
    try:
        env.seed(args.seed)
        obs = env.reset()
        return obs['agentview_image'][::-1], dict(task=suite.get_task(index).name, suite=suite_name, initial_state="simulator_reset")
    finally:
        env.close()


def robocasa(args):
    from robocasa.utils.env_utils import create_env
    task, split = args.task or 'OpenDrawer', args.suite or 'target'
    camera = 'robot0_agentview_left'
    env = create_env(env_name=task, split=split, seed=args.seed, camera_names=[camera])
    try:
        return env.reset()[camera+'_image'][::-1], dict(task=task, split=split, camera=camera)
    finally:
        env.close()


def robotwin(root, args):
    sys.path.insert(0, str(root/'scripts'))
    from eval_policy_xpolicylab import class_decorator, load_task_args
    task, config = args.task or 'beat_block_hammer', args.suite or 'demo_clean'
    options, _ = load_task_args(dict(task_name=task, task_config=config, policy_name='studio_observe'))
    options.update(render_freq=0, eval_mode=True)
    env = class_decorator(task)
    try:
        env.setup_demo(now_ep_num=0, seed=args.seed, is_test=True, **options)
        return env.get_obs()['observation']['head_camera']['rgb'], dict(task=task, config=config, camera='head_camera')
    finally:
        env.close_env()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('adapter', choices=('libero','libero-pro','robocasa','robotwin'))
    parser.add_argument('--suite', default='')
    parser.add_argument('--task', default='')
    parser.add_argument('--seed', default=0,type=int)
    args = parser.parse_args()
    root = Path(os.environ['RSI_ENV_ROOT']).resolve()
    out = Path(os.environ['LINKMIND_RUN_OUTPUT']).resolve()
    out.mkdir(parents=True,exist_ok=True)
    os.chdir(root)
    sys.path.insert(0, str(root))
    if sys.platform.startswith('linux') and args.adapter != 'robotwin':
        os.environ.setdefault('MUJOCO_GL', 'egl')
    if args.adapter.startswith('libero'):
        image, info = libero(root,out,args)
    elif args.adapter=='robocasa':
        image, info = robocasa(args)
    else:
        image, info = robotwin(root,args)
    from PIL import Image
    Image.fromarray(image).convert('RGB').save(out/'view.png')
    (out/'observation.json').write_text(json.dumps(dict(kind='reset_observation',adapter=args.adapter,
                                                       seed=args.seed, **info),indent=2))


if __name__=='__main__':
    main()
