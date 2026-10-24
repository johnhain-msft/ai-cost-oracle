"""Estimate logging, feedback, and calibration.

Every estimate is appended to ``estimates.jsonl`` with a short id. When the
user later reports the actual cost, the provider's calibration factor is
updated with an exponentially-weighted moving average of the actual/estimate
ratio (in log space, so over- and under-estimates pull symmetrically).
Future estimates are multiplied by the factor.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from corpus import oracle_home
from estimator import Estimate

EWMA_ALPHA = 0.30
CALIBRATION_FLOOR = 0.25
CALIBRATION_CEILING = 4.0


def estimates_path() -> Path:
    return oracle_home() / "estimates.jsonl"


def calibration_path() -> Path:
    return oracle_home() / "calibration.json"


def record_estimate(estimate: Estimate) -> None:
    path = estimates_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(estimate.to_dict()) + "\n")


def _read_estimates() -> list[dict]:
    path = estimates_path()
    if not path.is_file():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def find_estimate(estimate_id: str) -> dict:
    matches = [r for r in _read_estimates() if r.get("estimate_id") == estimate_id]
    if not matches:
        raise KeyError(f"No saved estimate with id '{estimate_id}'")
    return matches[-1]


def load_calibration() -> dict:
    path = calibration_path()
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def calibration_factor(provider: str) -> float:
    entry = load_calibration().get(provider, {})
    return float(entry.get("factor", 1.0))


def _updated_factor(current: float, actual: float, estimated: float) -> float:
    ratio = actual / estimated
    blended = math.exp(
        (1 - EWMA_ALPHA) * math.log(current) + EWMA_ALPHA * math.log(ratio)
    )
    return min(CALIBRATION_CEILING, max(CALIBRATION_FLOOR, blended))


def apply_feedback(estimate_id: str, actual: float) -> dict:
    """Record an actual cost against an estimate and recalibrate.

    Returns a report dict: the estimate, its signed error, and the
    provider's calibration factor before and after.
    """
    if actual <= 0:
        raise ValueError("Actual cost must be positive")
    saved = find_estimate(estimate_id)
    provider = saved["provider"]
    expected = float(saved["expected"])
    if expected <= 0:
        raise ValueError(f"Estimate {estimate_id} has no positive expected value")

    state = load_calibration()
    entry = state.get(provider, {"factor": 1.0, "samples": 0, "history": []})
    before = float(entry["factor"])
    after = _updated_factor(before, actual, expected)
    error_pct = (expected - actual) / actual * 100

    entry["factor"] = after
    entry["samples"] = int(entry.get("samples", 0)) + 1
    history: list[dict] = entry.get("history", [])
    history.append(
        {
            "estimate_id": estimate_id,
            "expected": expected,
            "actual": actual,
            "error_pct": round(error_pct, 2),
        }
    )
    entry["history"] = history[-50:]  # keep the recent window only
    state[provider] = entry

    path = calibration_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return {
        "estimate": saved,
        "actual": actual,
        "error_pct": error_pct,
        "factor_before": before,
        "factor_after": after,
        "samples": entry["samples"],
    }


def accuracy_report(provider: str) -> dict:
    """Mean absolute percentage error over the recorded feedback window."""
    entry = load_calibration().get(provider)
    if not entry or not entry.get("history"):
        return {"provider": provider, "samples": 0}
    errors = [abs(h["error_pct"]) for h in entry["history"]]
    return {
        "provider": provider,
        "samples": entry.get("samples", len(errors)),
        "factor": entry.get("factor", 1.0),
        "mape_pct": sum(errors) / len(errors),
    }
