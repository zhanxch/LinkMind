"""Instrument RRSI be50316 without modifying the upstream repository or judge."""
from __future__ import annotations

import contextvars
import functools
import importlib
import json
import os
import runpy
import subprocess
import tarfile
import tempfile
import uuid
import sys
from pathlib import Path

if __package__:
    from .rsi_flow import TRACE, emit, text
    from .rsi_validation import run_validators, validators_from
else:
    from rsi_flow import TRACE, emit, text
    from rsi_validation import run_validators, validators_from

ACTIVE = contextvars.ContextVar('rsi_round', default=None)
CANDIDATE = contextvars.ContextVar('rsi_candidate', default='')


class Observation:
    def __init__(self, instance, turn, trace):
        self.trace = Path(trace).resolve()
        self.instance = instance
        self.turn = turn
        self.name = os.environ.get('RSI_FLOW_RUN') or 'RRSI · '+instance.domain.name
        self.folder = instance.runs / f'r{turn}'
        self.references = set()

    def link(self, label, path):
        path = Path(path).resolve()
        if path.is_relative_to(self.trace.parent):
            return [{'label':label,'path':str(path.relative_to(self.trace.parent))}]
        return []

    def event(self, stage, status, *, turn=None, **fields):
        try:
            emit(self.trace, run=self.name, round=self.turn if turn is None else turn, stage=stage, status=status, **fields)
        except (OSError, ValueError) as exc:
            print(f'[studio observer] {exc}',file=sys.stderr,flush=True)


def full_commit(repo, ref):
    result = subprocess.run(['git','rev-parse','--verify',str(ref)+'^{commit}'], cwd=repo,
                            capture_output=True, text=True, check=True)
    return result.stdout.strip()


def record_loaded(ctx, harness):
    """Prove the next proposal actually received a checkout of the chosen revision."""
    if 'loaded' in ctx.references:
        return
    try:
        frontier = ctx.instance.frontier()
        history = frontier['trajectory']
        next_round = ctx.turn
        expected = full_commit(ctx.instance.repo, history[next_round]['commit'])
        if expected != full_commit(harness, 'HEAD'):
            return
        receipt = ctx.folder/'studio-base.json'
        receipt.write_text(json.dumps(dict(round=next_round, frontier_commit=expected,
                                          proposal_checkout_head=expected,
                                          candidate=CANDIDATE.get()), indent=2)+'\n')
        links = ctx.link('提案工作树与版本凭据',receipt)
        ctx.event('round','running',version=expected,links=links)
        if next_round > 0:
            fields = dict(turn=next_round-1, version=expected, loaded_in=next_round,
                          focus=f'第 {next_round} 轮的提案工作树已加载',links=links)
            ctx.event('loaded','loaded',**fields)
            incumbent = frontier['incumbent']
            if incumbent.get('t') == next_round and incumbent.get('variant'):
                ctx.event('loaded','loaded',candidate=incumbent['variant'],**fields)
        ctx.references.add('loaded')
    except (OSError, ValueError, KeyError, IndexError, subprocess.SubprocessError) as exc:
        print(f'[studio observer] could not verify loaded checkout: {exc}',file=sys.stderr,flush=True)


def validate_candidate(ctx, cand, folder, validators):
    """Validate the immutable Git candidate in a throwaway checkout."""
    def notify(check, status, reason, receipt, log):
        links = (ctx.link('运行凭据',receipt)+ctx.link('命令输出',log)) if receipt and log else []
        ctx.event('validation',status,candidate=cand.variant,check=check.id,required=check.required,
                  title=check.label,reason=reason,version=version,links=links)

    version = cand.commit
    try:
        version = full_commit(ctx.instance.repo, cand.commit)
        with tempfile.TemporaryDirectory(prefix='studio-validator-') as tmp:
            scratch=Path(tmp)
            checkout=scratch/'candidate'
            checkout.mkdir()
            archive=scratch/'source.tar'
            subprocess.run(['git','archive','--format=tar','-o',str(archive),version],
                           cwd=ctx.instance.repo, check=True, capture_output=True)
            with tarfile.open(archive) as source:
                source.extractall(checkout, filter='data')
            return run_validators(validators,checkout,folder/'validators'/uuid.uuid4().hex,notify,version=version,
                                  variables={'{python}':sys.executable,'{workspace}':ctx.trace.parent,'{diff}':folder/'diff.patch'})
    except (OSError, ValueError, tarfile.TarError, subprocess.SubprocessError) as exc:
        ctx.event('validation','error',candidate=cand.variant,check='validator-preparation',
                  title='候选副本准备',required=True,reason=text(str(exc)))
        return ['validator-preparation']


def instrument(loop, trace, validators=()):
    def hook(owner, name):
        def decorate(fn):
            original=getattr(owner,name)
            @functools.wraps(original)
            def call(*args,**kwargs):
                return fn(original,*args,**kwargs)
            setattr(owner,name,call)
            return call
        return decorate

    @hook(loop.Run,'round')
    def run_round(original, instance, t, dry_run=False):
        context=Observation(instance,t,trace)
        instance._studio_observation=context
        token=ACTIVE.set(context)
        context.event('round','running',workflow='coding',title=context.name,target=instance.domain.name)
        context.event('evidence','running',focus='选择当前版本的成功与失败轨迹')
        try:
            result=original(instance,t,dry_run=dry_run)
            context.event('round','done',reason='仅诊断' if dry_run else '')
            return result
        except BaseException as exc:
            context.event('round','failed',reason=text(str(exc)))
            raise
        finally:
            ACTIVE.reset(token)

    @hook(loop.Run,'save_frontier')
    def activate(original,instance,frontier):
        result=original(instance,frontier)
        ctx=ACTIVE.get()
        trajectory=frontier.get('trajectory') or []
        if ctx and len(trajectory)>ctx.turn+1:
            old,new=trajectory[ctx.turn:ctx.turn+2]
            changed=old.get('commit')!=new.get('commit')
            activation=dict(focus='更新下轮使用版本' if changed else '下一轮继续使用原版本',
                            version=full_commit(instance.repo,new['commit']),links=ctx.link('版本记录',instance.frontier_path))
            ctx.event('activation','adopted' if changed else 'retained',**activation)
            variant=frontier['incumbent'].get('variant')
            if changed and variant:
                ctx.event('activation','adopted',candidate=variant,**activation)
        return result

    for role in ('analyst','propose'):
        module=importlib.import_module('rrsi.'+role)

        @hook(module,'generate')
        def role_action(original,*args,**kwargs):
            response=original(*args,**kwargs)
            ctx=ACTIVE.get()
            if not ctx:
                return response
            try:
                action=json.loads(response)
            except (TypeError,ValueError):
                return response
            if isinstance(action,list):
                action=next((a for a in action if isinstance(a,dict)),None)
            if not isinstance(action,dict):
                return response
            name=action.get('action')
            if name=='digest_many':
                requests=action.get('requests')
                if isinstance(requests,list):
                    traces=[str(r.get('task_id')) for r in requests[:8] if isinstance(r,dict) and r.get('task_id')]
                    if traces:
                        ctx.event('evidence','running',focus='请求分析轨迹 '+', '.join(traces),metrics={'本批轨迹':len(traces)})
            elif name=='read_trace':
                ctx.event('proposal','running',candidate=CANDIDATE.get(),focus='请求查看轨迹 '+text(str(action.get('task_id')),110))
            elif name in ('edit_file','write_file'):
                ctx.event('proposal','running',candidate=CANDIDATE.get(),focus='请求写入 '+text(action.get('path'),130))
            return response

    @hook(loop.Run,'build_traces')
    def evidence(original,instance,job,per_task):
        traces=original(instance,job,per_task)
        ctx=ACTIVE.get()
        if ctx:
            ctx.event('evidence','running',focus='分析选中的基线轨迹',metrics={'轨迹':len(traces)})
        return traces

    @hook(loop,'analyze')
    def analyze(original,*args,**kwargs):
        report=original(*args,**kwargs)
        ctx=ACTIVE.get()
        if ctx:
            modes=[text(r.get('mode'),100) for r in report.get('failure_modes') or [] if isinstance(r,dict)]
            ctx.event('evidence','done',focus=' · '.join(m for m in modes[:3] if m) or '诊断完成',
                      links=ctx.link('诊断报告',ctx.folder/'analysis_report.json'))
        return report

    @hook(loop.Run,'_draft')
    def draft(original, instance, t, variant, rdir, *args, **kwargs):
        ctx=ACTIVE.get()
        if not ctx:
            return original(instance,t,variant,rdir,*args,**kwargs)
        token=CANDIDATE.set(variant)
        try:
            report_path=Path(rdir)/'analysis_report.json'
            directives_path=Path(rdir)/'directives.json'
            from_json=lambda p: json.loads(p.read_text())
            directives=from_json(directives_path)
            if not ctx.references:
                ctx.references.add('analysis')
                modes=[text(v.get('mode'),100) for v in from_json(report_path).get('failure_modes',[]) if isinstance(v,dict)]
                ctx.event('evidence','done',focus=' · '.join(modes[:3]) or '诊断完成',
                          metrics={'编辑预算':directives.get('b_t'),'噪声带':directives.get('delta')},
                          links=ctx.link('诊断报告',report_path)+ctx.link('本轮搜索约束',directives_path))
            ctx.event('proposal','running',candidate=variant,focus='提出并应用 harness 改动')
            cand=original(instance,t,variant,rdir,*args,**kwargs)
            folder=Path(rdir)/variant
            edits=cand.edits or []
            if edits:
                ctx.event('proposal','done',candidate=variant,
                          focus=' · '.join(text(v.get('targets_mode'),90) for v in edits if isinstance(v,dict)),
                          change=' · '.join(text(v.get('component'),80) for v in edits if isinstance(v,dict)),
                          hypothesis=' · '.join(text(v.get('hypothesis'),130) for v in edits if isinstance(v,dict)),
                          metrics={'改动数':len(edits)},links=ctx.link('候选差异',folder/'diff.patch')+
                          ctx.link('候选提案',folder/'proposal.json'))
            elif cand.gate_failure=='no_proposal':
                ctx.event('proposal','skipped',candidate=variant,reason=text(cand.detail))
                return cand
            rejected=cand.gate_failure=='critic_reject'
            ctx.event('review','rejected' if rejected else 'passed',candidate=variant,focus='评测泄漏审查',
                      reason=text(cand.detail) if rejected else '',version=cand.commit or '',
                      links=ctx.link('审查记录',folder/'critic.json'))
            smoke_path=folder/'smoke.json'
            if smoke_path.is_file():
                passed=from_json(smoke_path).get('ok') is True
                ctx.event('validation','passed' if passed else 'failed',candidate=variant,check='native-smoke',
                          title='RRSI 原生自检',required=True,reason=text(cand.detail) if not passed else '',
                          version=cand.commit or '',links=ctx.link('自检凭据',smoke_path))
            if validators and cand.gate_failure is None:
                failed = validate_candidate(ctx,cand,folder,validators)
                if failed:
                    cand.gate_failure='validator_failed'
                    cand.detail='Required validation failed: '+', '.join(failed)
            return cand
        finally:
            CANDIDATE.reset(token)

    @hook(loop,'propose')
    def propose(original,domain,harness,*args,**kwargs):
        ctx=ACTIVE.get()
        if ctx and not kwargs.get('repair_brief'):
            record_loaded(ctx,harness)
        if ctx and kwargs.get('repair_brief'):
            ctx.event('proposal','running',candidate=CANDIDATE.get(),focus='修订审查意见中的问题')
        proposal=original(domain,harness,*args,**kwargs)
        if ctx and proposal.get('status')=='done':
            edits=proposal.get('edits') or []
            ctx.event('proposal','done',candidate=CANDIDATE.get(),title=text(proposal.get('summary')),
                      focus=' · '.join(text(e.get('targets_mode'),90) for e in edits if isinstance(e,dict)),
                      change=' · '.join(text(e.get('component'),80) for e in edits if isinstance(e,dict)),
                      metrics={'改动数':len(edits)})
        return proposal

    @hook(loop,'review')
    def review(original,*args,**kwargs):
        ctx=ACTIVE.get()
        if ctx:
            ctx.event('review','running',candidate=CANDIDATE.get(),focus='核对差异中的评测泄漏')
        return original(*args,**kwargs)

    @hook(loop.Run,'_evaluate')
    def evaluate(original,instance,t,c,rdir,ids):
        ctx=getattr(instance,'_studio_observation',None)
        if ctx:
            ctx.event('evaluation','running',candidate=c.variant,focus='运行演化评估集',
                      metrics={'计划试次':len(ids)*instance.cfg.k})
        result=original(instance,t,c,rdir,ids)
        if ctx:
            ev=c.ev
            ctx.event('evaluation','done' if ev else 'failed',candidate=c.variant,
                      focus='原生评估返回',reason=text(c.detail),
                      metrics={'分数':ev.S,'推理 token':ev.C,'缺失':ev.missing} if ev else {},
                      progress={'done':ev.n_expected-ev.missing,'total':ev.n_expected} if ev else {},
                      links=ctx.link('逐例评估',Path(rdir)/c.variant/'eval.json'))
        return result

    @hook(loop,'select_round')
    def select(original,cands,incumbent,high,delta,*args,**kwargs):
        ctx=ACTIVE.get()
        if ctx:
            ctx.event('decision','running',focus='核对噪声、成本与域约束')
        winner, decisions=original(cands,incumbent,high,delta,*args,**kwargs)
        if ctx:
            from rrsi.selection import cost_rule
            for c,d in zip(cands,decisions):
                status='done' if c is winner else 'admissible' if d.admissible else 'rejected'
                checks={'可接受':d.admissible}
                if d.S is not None:
                    checks.update({'噪声调整后的下限':high-delta,'分数达到下限':d.S>=high-delta,
                                   '成本规则通过':cost_rule(d.delta_S,d.delta_C,d.novelty,delta,ctx.instance.cfg)[0],
                                   '域约束通过':not d.guards,
                                   '两版均记录 token':incumbent.C is not None and d.C is not None})
                ctx.event('decision',status,candidate=c.variant,focus='选中，等待写入下轮' if c is winner else
                          '符合门槛，未胜出' if d.admissible else '未采用',reason=d.reason,
                          metrics={'分数变化':d.delta_S,'token 相对变化':d.delta_C},checks=checks,
                          links=ctx.link('完整选择记录',ctx.folder/'decisions.json'))
            ctx.event('decision','done',focus='选中 '+winner.variant if winner else '无可接受候选')
        return winner,decisions


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('upstream',nargs='?',default=os.environ.get('RSI_UPSTREAM_ENTRY'))
    if os.environ.get('RSI_UPSTREAM_ENTRY'):
        entry=Path(os.environ['RSI_UPSTREAM_ENTRY']).resolve()
        rest=sys.argv[1:]
    else:
        args,rest=parser.parse_known_args(sys.argv[1:2])
        if not args.upstream:
            parser.error('Supply the upstream rrsi.py path')
        entry=Path(args.upstream).resolve()
        rest=sys.argv[2:]
    if not entry.is_file() or entry.name!='rrsi.py':
        parser.error('Expected a checkout with the upstream rrsi.py entry')
    trace=Path(os.environ.get('RSI_FLOW_PATH', TRACE)).resolve()
    sys.path.insert(0,str(entry.parent))
    os.environ.update(RSI_UPSTREAM_ENTRY=str(entry),RSI_FLOW_PATH=str(trace))
    from rrsi import driver, loop
    drive=driver.drive
    def traced_driver(_entry,*args,**kwargs):
        return drive(Path(__file__).resolve(),*args,**kwargs)
    driver.drive=traced_driver
    instrument(loop,trace,validators_from(os.environ.get('RSI_VALIDATORS')))
    sys.argv=[str(entry),*rest]
    runpy.run_path(str(entry),run_name='__main__')


if __name__=='__main__':
    main()
