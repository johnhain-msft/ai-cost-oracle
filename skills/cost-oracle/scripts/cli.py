#!/usr/bin/env python3
"""cost-oracle — predict the cost of an AI request before you spend it.

Commands:
  train      Build the baseline corpus from local session history
  estimate   Estimate the cost of a task (USD for Claude, AIC for Copilot)
  feedback   Report an actual cost to recalibrate future estimates
  status     Show corpus, calibration, and accuracy state
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import corpus as corpus_module
import estimator
import feedback as feedback_module
from pricing import CLAUDE_PRICES


def _fmt(value: float, unit: str) -> str:
    return f"${value:,.2f}" if unit == "USD" else f"{value:,.2f} AIC"


def cmd_train(args: argparse.Namespace) -> int:
    claude_dir = Path(args.claude_dir) if args.claude_dir else None
    copilot_db = Path(args.copilot_db) if args.copilot_db else None
    built = corpus_module.build(claude_dir=claude_dir, copilot_db=copilot_db)
    target = corpus_module.save(built)
    providers = built["providers"]
    print(f"Training round complete -> {target}")
    for name, section in providers.items():
        models = ", ".join(sorted(section.get("models", {}))) or "none"
        print(
            f"  {name:<8} {section['requests']:>7,} requests "
            f"across {section['sessions']:>5,} sessions | models: {models}"
        )
    return 0


def _print_estimate(result: estimator.Estimate, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result.to_dict(), indent=2))
        return
    unit = result.unit
    print(f"Estimate [{result.estimate_id}]  {result.provider} / {result.model}")
    if result.task:
        print(f"  task:       {result.task}")
    print(f"  complexity: {result.complexity} (~{result.n_requests:.0f} requests)")
    print(f"  expected:   {_fmt(result.expected, unit)}")
    print(f"  range:      {_fmt(result.low, unit)} - {_fmt(result.high, unit)}")
    print(f"  basis:      {result.basis}")
    if abs(result.calibration - 1.0) > 1e-9:
        print(f"  calibration: x{result.calibration:.3f} (learned from feedback)")
    print(f"  feedback:   cost-oracle feedback {result.estimate_id} --actual <cost>")


def cmd_estimate(args: argparse.Namespace) -> int:
    trained = corpus_module.load()
    calibration = feedback_module.calibration_factor(args.provider)
    estimate_fn = (
        estimator.estimate_claude
        if args.provider == "claude"
        else estimator.estimate_copilot
    )
    result = estimate_fn(
        trained,
        model=args.model,
        task=args.task or "",
        complexity=args.complexity,
        calibration=calibration,
        n_requests=args.requests,
    )
    feedback_module.record_estimate(result)
    _print_estimate(result, args.json)
    if args.budget is not None:
        fits = result.expected <= args.budget
        verdict = "FITS" if fits else "EXCEEDS"
        print(
            f"  budget:     {_fmt(args.budget, result.unit)} -> "
            f"{verdict} (expected {_fmt(result.expected, result.unit)})"
        )
        return 0 if fits else 2
    return 0


def cmd_feedback(args: argparse.Namespace) -> int:
    report = feedback_module.apply_feedback(args.estimate_id, args.actual)
    saved = report["estimate"]
    unit = saved.get("unit", "USD")
    direction = "over" if report["error_pct"] > 0 else "under"
    print(f"Feedback recorded for [{args.estimate_id}] ({saved['provider']})")
    print(f"  estimated: {_fmt(float(saved['expected']), unit)}")
    print(f"  actual:    {_fmt(report['actual'], unit)}")
    print(f"  error:     {abs(report['error_pct']):.1f}% {direction}-estimated")
    print(
        f"  calibration: x{report['factor_before']:.3f} -> x{report['factor_after']:.3f} "
        f"({report['samples']} feedback samples)"
    )
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    del args
    try:
        trained = corpus_module.load()
    except FileNotFoundError as error:
        print(error)
        return 1
    print(f"Corpus trained at {trained['trained_at']}")
    for name, section in trained["providers"].items():
        print(
            f"  {name}: {section['requests']:,} requests, {section['sessions']:,} sessions"
        )
    for provider in ("claude", "copilot"):
        report = feedback_module.accuracy_report(provider)
        if report.get("samples"):
            print(
                f"  {provider} calibration x{report['factor']:.3f} | "
                f"MAPE {report['mape_pct']:.1f}% over {report['samples']} samples"
            )
    return 0


def cmd_models(args: argparse.Namespace) -> int:
    del args
    print("Claude models (USD per 1M tokens in/out):")
    for model, price in sorted(CLAUDE_PRICES.items()):
        print(
            f"  {model:<22} ${price.input_per_mtok:>5.2f} / ${price.output_per_mtok:>6.2f}"
        )
    print("Copilot models: learned from session history (run: cost-oracle status)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cost-oracle", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    train = sub.add_parser(
        "train", help="Build the baseline corpus from session history"
    )
    train.add_argument("--claude-dir", help="Override ~/.claude/projects")
    train.add_argument("--copilot-db", help="Override ~/.copilot/session-store.db")
    train.set_defaults(func=cmd_train)

    est = sub.add_parser("estimate", help="Estimate the cost of a task")
    est.add_argument("--provider", choices=("claude", "copilot"), required=True)
    est.add_argument("--model", required=True, help="Model id, e.g. claude-opus-5")
    est.add_argument(
        "--task", help="Short description of the task (recorded with the estimate)"
    )
    est.add_argument(
        "--complexity",
        choices=sorted(estimator.TIERS),
        default="moderate",
        help="Task size tier (default: moderate)",
    )
    est.add_argument(
        "--requests", type=float, help="Override the expected request count"
    )
    est.add_argument(
        "--budget",
        type=float,
        help="Check the estimate against a budget; exit code 2 if it exceeds",
    )
    est.add_argument("--json", action="store_true", help="Emit the estimate as JSON")
    est.set_defaults(func=cmd_estimate)

    back = sub.add_parser("feedback", help="Report the actual cost of an estimate")
    back.add_argument("estimate_id", help="Id printed with the estimate")
    back.add_argument(
        "--actual", type=float, required=True, help="Actual cost (USD or AIC)"
    )
    back.set_defaults(func=cmd_feedback)

    sub.add_parser("status", help="Show corpus and calibration state").set_defaults(
        func=cmd_status
    )
    sub.add_parser("models", help="List known model pricing").set_defaults(
        func=cmd_models
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, KeyError, FileNotFoundError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
