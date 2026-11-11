"""Read-only evaluation audit; output is separate from frozen candidate sources."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from roborag.episode_files import read_json, read_jsonl, write_json
from roborag.rag_accounting import control_accounting, workflow_completed


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def case_key(row):
    return row["seed"], row["variant"], row["layout"]


def counts(rows):
    successes=sum(row["success"] is True for row in rows)
    failures=sum(row["success"] is False for row in rows)
    scored=successes+failures
    return dict(attempts_closed=len(rows),success=successes,failure=failures,unscored=len(rows)-scored,
                scored=scored,success_rate_scored=successes/scored if scored else None,
                confirmed_success_fraction_closed=successes/len(rows) if rows else None)


def costs(rows):
    values={name:[] for name in ("steps","wall_seconds","input_tokens","cached_input_tokens",
            "output_tokens","reasoning_output_tokens","total_tokens","uncached_input_tokens")}
    for row in rows:
        usage=row["usage"] or {}
        for name in ("steps","wall_seconds"):
            values[name].append(row[name])
        for name in ("input_tokens","cached_input_tokens","output_tokens","reasoning_output_tokens"):
            values[name].append(usage.get(name))
        i,o,c=(usage.get(name) for name in ("input_tokens","output_tokens","cached_input_tokens"))
        values["total_tokens"].append(i+o if i is not None and o is not None else None)
        values["uncached_input_tokens"].append(i-c if i is not None and c is not None else None)
    result={}
    for name,items in values.items():
        known=[value for value in items if value is not None]
        result[name]=dict(known_count=len(known),unknown_count=len(items)-len(known),
                          known_sum=sum(known) if known else None,
                          known_mean=statistics.mean(known) if known else None)
    result["steps"]["partial_lower_bound_cases"]=sum(not row["steps_complete"] for row in rows)
    return result


def validated_native_score(raw, record):
    """Missing/invalid outcome fields are unscored; never infer failure from them."""
    if not isinstance(raw, dict) or raw.get("eval_time") != 1 or raw.get("policy_error"):
        return None, ["native_evaluation_incomplete_or_policy_error"]
    details = raw.get("details")
    detail = details.get("0") if isinstance(details, dict) else None
    if not isinstance(detail, dict) or len(details) != 1:
        return None, ["native_single_scene_detail_missing"]
    assert detail.get("layout_id") == record["layout"], "Native score belongs to a different layout"
    rate, score = raw.get("success_rate"), raw.get("score")
    if type(rate) not in (int, float) or not math.isfinite(rate) or rate not in (0, 1):
        return None, ["native_binary_success_rate_missing_or_invalid"]
    if type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 100:
        return None, ["native_progress_score_missing_or_invalid"]
    if type(detail.get("success")) is not bool:
        return None, ["native_per_scene_success_missing_or_invalid"]
    assert detail["success"] == (rate == 1), "Native aggregate and scene verdict disagree"
    return raw, []


def audit_case(record, freeze):
    directory=Path(record["output"])
    config=read_json(directory/"run.json")
    assert config is not None, f"Missing launch provenance: {directory}"
    assert config["git_commit"]==freeze["candidate_commit"], directory
    assert config["prompt_sha256"]==freeze["prompt_sha256"]
    prompt=directory/"agent-prompt.txt"
    if prompt.exists():assert digest(prompt)==config["prompt_sha256"]
    for path,sha in config["source_sha256"].items():
        assert freeze["source_sha256"][str(Path(path).resolve())]==sha, path
    for name in ("seed","variant","layout"):
        assert config["args"][name]==record[name]
    task=freeze["task"]["task"]
    assert config["args"]["task"]==task, "Runner task differs from the frozen task"
    expected_native_task=task+("_random" if record["variant"]=="random" else "")
    assert config["task"]==expected_native_task, "Native task/variant differs from the registered scene"
    for name in ("model","effort","controller","max_wall_seconds"):
        assert config["args"][name]==freeze["conditions"][name]
    assert Path(config["args"]["bank"]).resolve()==(ROOT/freeze["task"]["bank"]).resolve()
    layout=ROOT/f"data/Assets/Eval_Layout/RoboDojo/arx_x5/{record['seed']}/{config['task']}_{record['layout']}.json"
    assert digest(layout)==config["layout_sha256"]==freeze["source_sha256"][str(layout.resolve())]
    ready=read_json(directory/"ready.json")
    if ready:
        assert ready["step_limit"]==freeze["task"]["native_step_limits"][record["variant"]]
        if freeze["conditions"].get("ik_guard"):
            expected_guard = {k: freeze["conditions"]["ik_guard"][k]
                              for k in ("kind", "max_joint_increment_rad")}
            assert ready["execution_guard"] == config["execution_guard"] == expected_guard
    calls, malformed_calls=read_jsonl(directory/"mcp-calls.jsonl")
    commands, malformed_commands=read_jsonl(directory/"commands.jsonl")
    accounting=control_accounting(directory,calls)
    problems=[]
    for name,value in ("mcp",malformed_calls),("commands",malformed_commands),("actions",accounting["malformed_action_records"]):
        if value:problems.append(f"{name}: {value} malformed records")
    for command in commands:
        snapshot=Path(command["observation"])
        for name in ("state.json","head.png","wrist_l.png","wrist_r.png"):
            if not (snapshot/name).is_file():problems.append(f"Missing trajectory artifact: {snapshot/name}")
        state=read_json(snapshot/"state.json")
        if state is not None and state["step"]!=command["step_after"]:
            problems.append(f"Observation counter differs: {snapshot}")
    result=read_json(directory/"result.json")
    raw_files=list(directory.rglob("_result.json"))
    assert len(raw_files)<=1, "Multiple native scores for one attempt"
    native=None
    native_scoring_issues=[]
    if raw_files:
        raw=read_json(raw_files[0])
        native,native_scoring_issues=validated_native_score(raw,record)
    # The batch captures this receipt when the episode exits. Compare against
    # that independent completed-attempt snapshot as well as result.json.
    saved_result=record.get("result")
    if saved_result:
        assert saved_result["complete"] and native==saved_result["native"]
        assert len(raw_files)==1 and digest(raw_files[0])==saved_result["native_sha256"], (
            "Native result differs from its completed-attempt receipt")
        assert Path(saved_result["native_result"]).resolve()==raw_files[0].resolve()
    if result:
        assert native==result["native"] and result["complete"]
        assert digest(raw_files[0])==result["native_sha256"]
        assert result["native_control_steps"]==accounting["native_control_steps"]
    agent=read_json(directory/"agent-exit.json",{})
    failure=read_json(directory/"exit.json") or read_json(directory/"sim_failure.json")
    wall=(result or failure or {}).get("wall_seconds")
    if wall is None:wall=record["ended_epoch"]-record["started_epoch"]
    files=[directory/name for name in ("run.json","result.json","agent-exit.json","agent-prompt.txt",
           "actions.jsonl","commands.jsonl","mcp-calls.jsonl","gpt-plan.json","episode_end.json",
           "ready.json","exit.json","sim_failure.json")]
    return dict(seed=record["seed"],variant=record["variant"],layout=record["layout"],
        directory=str(directory),returncode=record["returncode"],success=None if native is None else native["success_rate"]==1,
        native_score=None if native is None else native.get("score"),
        native_result=str(raw_files[0]) if native is not None else None,
        native_sha256=digest(raw_files[0]) if native is not None else None,
        native_scoring_issues=native_scoring_issues,
        native_without_runner_summary=native is not None and result is None,
        failure=failure,steps=accounting["native_control_steps"],steps_complete=accounting["native_control_steps_complete"],
        wall_seconds=wall,usage=agent.get("usage"),layout_sha256=config["layout_sha256"],
        workflow_verified=workflow_completed(calls),trajectory_problems=problems,
        command_count=len(commands),tool_counts={name:sum(c["tool"]==name for c in calls) for name in sorted({c["tool"] for c in calls})},
        artifact_sha256={str(p):digest(p) for p in [*files,*raw_files] if p.exists()})


def audit_task(tag, expected_commit, protocol, protocol_sha256):
    freeze_path=ROOT/"runs"/f"{tag}-freeze.json"
    freeze=read_json(freeze_path)
    assert freeze["candidate_commit"] == expected_commit, f"Mixed candidate revision: {tag}"
    protocol_path = Path(freeze["protocol"])
    assert Path(freeze["protocol"]).resolve() == protocol_path.resolve()
    assert freeze["source_sha256"][str(protocol_path.resolve())] == protocol_sha256
    assert freeze["conditions"] == protocol["conditions"], f"Mixed conditions: {tag}"
    registered = next(t for t in protocol["tasks"] if t["task"] == freeze["task"]["task"])
    assert freeze["task"] == registered, f"Unregistered task configuration: {tag}"
    source_count=0
    for path,sha in freeze["source_sha256"].items():
        assert digest(path)==sha, f"Frozen source drift: {path}"
        source_count+=1
    status_path=ROOT/"runs"/tag/"status.json"
    status_bytes=status_path.read_bytes()
    status=json.loads(status_bytes)
    status_sha256=hashlib.sha256(status_bytes).hexdigest()
    declared=read_json(ROOT/freeze["task"]["cases_file"])
    expected={case_key(row) for row in declared}
    batch=read_json(ROOT/"runs"/tag/"batch.json")
    assert batch["task"]==freeze["task"]["task"] and batch["no_rag"] is False
    assert Path(batch["bank"]).resolve()==(ROOT/freeze["task"]["bank"]).resolve()
    for name in ("parallel","model","effort","controller","max_wall_seconds"):
        assert batch[name]==freeze["conditions"][name], f"Batch condition differs: {tag} {name}"
    assert batch["source_sha256"]==freeze["source_sha256"], "Batch source inventory differs from freeze"
    assert batch["cases"]==declared, "Batch launch order or scene list differs from registration"
    keys=[case_key(row) for row in status["finished"]]
    assert len(keys)==len(set(keys)) and set(keys)<=expected
    active_keys=[case_key(row) for row in status["active"].values()]
    pending_keys=[case_key(row) for row in status["pending"]]
    all_keys=keys+active_keys+pending_keys
    assert len(all_keys)==len(set(all_keys)) and set(all_keys)==expected, f"Duplicate or omitted scene: {tag}"
    assert len(keys)+len(status["active"])+len(status["pending"])==len(expected)==freeze["task"]["case_count"]
    if status["complete"]:assert set(keys)==expected
    rows=[audit_case(row,freeze) for row in status["finished"]]
    # Once a task's first pass has been sealed, later suite audits must also
    # match those saved results rather than merely regenerate new hashes.
    launch=read_json(ROOT/"runs"/f"{tag}-launch.json",{})
    if launch.get("first_pass_audit_report"):
        saved_path=Path(launch["first_pass_audit_report"])
        assert digest(saved_path)==launch["first_pass_audit_sha256"], "Sealed task report changed"
        saved=read_json(saved_path)
        assert status["complete"] and saved["complete"]
        assert saved["candidate_commit"]==freeze["candidate_commit"]
        assert saved["audit"]["freeze_sha256"]==digest(freeze_path)
        assert saved["audit"]["status_sha256"]==status_sha256
        earlier={case_key(row):row for row in saved["cases"]}
        assert set(earlier)==set(keys)
        for row in rows:
            previous=earlier[case_key(row)]
            for field in ("success","native_sha256","layout_sha256","artifact_sha256",
                          "steps","steps_complete","usage","wall_seconds"):
                assert row[field]==previous[field], f"Sealed attempt changed: {tag} {case_key(row)} {field}"
    if launch.get('skip_audit_report'):
        saved_path=Path(launch['skip_audit_report'])
        assert digest(saved_path)==launch['skip_audit_sha256'], 'Sealed skipped-task report changed'
        saved=read_json(saved_path)
        assert saved['skipped'] and not status['complete'] and not status['active']
        assert saved['candidate_commit']==freeze['candidate_commit']
        assert saved['audit']['freeze_sha256']==digest(freeze_path)
        assert saved['audit']['status_sha256']==status_sha256
        assert saved['unstarted_skipped_cases']==status['pending']
        earlier={case_key(row):row for row in saved['cases']}
        assert set(earlier)==set(keys)
        for row in rows:
            for field in ('success','native_sha256','layout_sha256','artifact_sha256','steps','steps_complete','usage','wall_seconds'):
                assert row[field]==earlier[case_key(row)][field], f'Skipped attempt changed: {tag} {case_key(row)} {field}'
    variants={v:counts([c for c in rows if c["variant"]==v]) for v in ("standard","random")}
    complete_scored=status["complete"] and all(c["success"] is not None for c in rows)
    return dict(task=freeze["task"]["task"],tag=tag,complete=status["complete"],
        candidate_commit=freeze["candidate_commit"],counts=counts(rows),variants=variants,cases=rows,
        equal_variant_weight_success_rate=sum(v["success_rate_scored"] for v in variants.values())/2 if complete_scored else None,
        all_attempt_costs=costs(rows),batch_wall_seconds=status["wall_seconds"],
        audit=dict(passed=not any(c["trajectory_problems"] for c in rows),frozen_sources_verified=source_count,
                   candidate_matches_registered_suite=True,conditions_match_registered_suite=True,
                   batch_configuration_verified=True,scene_task_and_layout_sources_verified=True,
                   native_results_verified=sum(c["native_result"] is not None for c in rows),
                   trajectories_checked=len(rows),freeze_sha256=digest(freeze_path),status_sha256=status_sha256),
        active=list(status["active"]),pending=len(status["pending"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--protocol", type=Path,
                        default=ROOT / "experiments/push_T/current-v3-full50-20261103.json")
    args = parser.parse_args()
    protocol_path = args.protocol.resolve()
    protocol = read_json(protocol_path)
    freeze = read_json(ROOT / "runs" / f"{args.tag}-freeze.json")
    assert Path(freeze["protocol"]).resolve() == protocol_path
    report = audit_task(args.tag, freeze["candidate_commit"], protocol, digest(protocol_path))
    report.update(schema="roborag.push-t-current-audit.v1", generated_at=datetime.now(timezone.utc).isoformat(),
        protocol_sha256=digest(protocol_path), base_commit=protocol["base_commit"],
        interpretation=protocol["scope"]["interpretation"], actual_billed_usd=None)
    for variant, values in report["variants"].items():
        scores = [row["native_score"] for row in report["cases"] if row["variant"] == variant and row["native_score"] is not None]
        values["mean_native_score_scored"] = statistics.mean(scores) if scores else None
    scores = [row["native_score"] for row in report["cases"] if row["native_score"] is not None]
    report["mean_native_score_scored"] = statistics.mean(scores) if scores else None
    write_json(args.output, report)
    print(json.dumps({k: report[k] for k in ("complete", "candidate_commit", "counts", "mean_native_score_scored", "audit")}, ensure_ascii=False))
    if not report["audit"]["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
