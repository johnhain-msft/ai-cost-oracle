"""Turn the trained corpus into a cost estimate for a described task.

Claude estimates are token-based: per-request token distributions from the
corpus are priced at the requested model's published rates. Copilot
estimates are AIC-based: the per-request AIC distribution is used directly.
Complexity tiers anchor to percentiles of observed behavior, and the
provider's calibration factor (learned from feedback) scales the result.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from pricing import TokenUsage, claude_request_cost_usd
from stats_util import PERCENTILE_KEYS

TIERS: dict[str, str] = {
    "quick": "p10",
    "simple": "p25",
    "moderate": "p50",
    "complex": "p75",
    "epic": "p90",
}
_RANGE_OFFSET = 1  # low/high are one percentile band either side of expected


@dataclass(frozen=True)
class Estimate:
    """A saved, feedback-ready cost estimate."""

    estimate_id: str
    created_at: str
    provider: str
    model: str
    task: str
    complexity: str
    n_requests: float
    unit: str
    expected: float
    low: float
    high: float
    calibration: float
    basis: str

    def to_dict(self) -> dict:
        return asdict(self)


def _band_keys(tier: str) -> tuple[str, str, str]:
    center = TIERS[tier]
    index = PERCENTILE_KEYS.index(center)
    low = PERCENTILE_KEYS[max(0, index - _RANGE_OFFSET)]
    high = PERCENTILE_KEYS[min(len(PERCENTILE_KEYS) - 1, index + _RANGE_OFFSET)]
    return low, center, high


def _model_stats(section: dict, model: str, min_samples: int) -> tuple[dict, str]:
    """Prefer the model's own history; fall back to the all-model baseline."""
    model_entry = section.get("models", {}).get(model)
    if model_entry:
        per_request = model_entry.get("cost_usd_per_request") or model_entry.get(
            "aic_per_request", {}
        )
        if per_request.get("count", 0) >= min_samples:
            return model_entry, f"{model} history"
    return section["all_models"], "all-model baseline"


def _tokens_at(tokens_per_request: dict, key: str) -> TokenUsage:
    def value(field: str) -> float:
        stats = tokens_per_request.get(field, {})
        return float(stats.get(key, 0) or 0)

    return TokenUsage(
        input_tokens=value("input_tokens"),
        output_tokens=value("output_tokens"),
        cache_read_tokens=value("cache_read_tokens"),
        cache_write_5m_tokens=value("cache_write_5m_tokens"),
        cache_write_1h_tokens=value("cache_write_1h_tokens"),
    )


def _requests_for_tier(section: dict, tier: str, explicit: float | None) -> float:
    if explicit is not None:
        if explicit <= 0:
            raise ValueError("--requests must be positive")
        return explicit
    per_session = section.get("requests_per_session", {})
    return max(1.0, float(per_session.get(TIERS[tier], 1) or 1))


def _new_estimate(**kwargs: object) -> Estimate:
    return Estimate(
        estimate_id=uuid.uuid4().hex[:8],
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **kwargs,  # type: ignore[arg-type]
    )


def estimate_claude(
    corpus: dict,
    model: str,
    task: str,
    complexity: str,
    calibration: float,
    n_requests: float | None = None,
    min_samples: int = 15,
) -> Estimate:
    section = corpus["providers"]["claude"]
    if section.get("requests", 0) == 0:
        raise ValueError("Claude corpus is empty — no session history was found")
    stats, basis = _model_stats(section, model, min_samples)
    tokens = stats["tokens_per_request"]
    low_key, mid_key, high_key = _band_keys(complexity)
    requests = _requests_for_tier(section, complexity, n_requests)
    per_request = {
        key: claude_request_cost_usd(model, _tokens_at(tokens, key))
        for key in (low_key, mid_key, high_key)
    }
    return _new_estimate(
        provider="claude",
        model=model,
        task=task,
        complexity=complexity,
        n_requests=requests,
        unit="USD",
        expected=per_request[mid_key] * requests * calibration,
        low=per_request[low_key] * requests * calibration,
        high=per_request[high_key] * requests * calibration,
        calibration=calibration,
        basis=f"tokens/request from {basis}, priced at {model} rates",
    )


def estimate_copilot(
    corpus: dict,
    model: str,
    task: str,
    complexity: str,
    calibration: float,
    n_requests: float | None = None,
    min_samples: int = 15,
) -> Estimate:
    section = corpus["providers"]["copilot"]
    if section.get("requests", 0) == 0:
        raise ValueError("Copilot corpus is empty — no session history was found")
    stats, basis = _model_stats(section, model, min_samples)
    aic = stats["aic_per_request"]
    low_key, mid_key, high_key = _band_keys(complexity)
    requests = _requests_for_tier(section, complexity, n_requests)
    return _new_estimate(
        provider="copilot",
        model=model,
        task=task,
        complexity=complexity,
        n_requests=requests,
        unit="AIC",
        expected=float(aic[mid_key]) * requests * calibration,
        low=float(aic[low_key]) * requests * calibration,
        high=float(aic[high_key]) * requests * calibration,
        calibration=calibration,
        basis=f"AIC/request from {basis}",
    )
