"""Explicit per-run control budgets; omitting an override keeps native limits."""
import argparse


def positive_step_limit(value):
    try:
        limit = int(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError("control step limit must be a positive integer") from None
    if isinstance(value, bool) or str(limit) != str(value) or limit <= 0:
        raise argparse.ArgumentTypeError("control step limit must be a positive integer")
    return limit


def add_budget_argument(parser):
    parser.add_argument("--control-step-limit", type=positive_step_limit, default=None,
                        help="Explicit modified-budget experiment; default keeps the native task limit")


def budget_arguments(limit):
    return [] if limit is None else ["--control-step-limit", str(positive_step_limit(limit))]


def apply_control_budget(env, limit):
    native_limit = int(env.step_lim)
    if limit is not None:
        env.step_lim = positive_step_limit(limit)
    return dict(native_step_limit=native_limit, control_step_limit_override=limit,
                step_limit=int(env.step_lim), budget_mode="native" if limit is None else "modified")
