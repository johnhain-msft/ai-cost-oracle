"""Small statistics helpers shared by the corpus builder and estimator."""

from __future__ import annotations

PERCENTILE_KEYS: tuple[str, ...] = ("p10", "p25", "p50", "p75", "p90")
_PERCENTILE_VALUES: dict[str, float] = {
    "p10": 0.10,
    "p25": 0.25,
    "p50": 0.50,
    "p75": 0.75,
    "p90": 0.90,
}


def percentile(sorted_values: list[float], fraction: float) -> float:
    """Linear-interpolation percentile over an already-sorted list."""
    if not sorted_values:
        raise ValueError("percentile() requires at least one value")
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = fraction * (len(sorted_values) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = rank - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def summarize(values: list[float]) -> dict[str, float]:
    """Return count/mean/percentile summary for a list of observations."""
    if not values:
        return {"count": 0}
    ordered = sorted(values)
    summary: dict[str, float] = {
        "count": len(ordered),
        "mean": sum(ordered) / len(ordered),
    }
    for key, fraction in _PERCENTILE_VALUES.items():
        summary[key] = percentile(ordered, fraction)
    return summary
