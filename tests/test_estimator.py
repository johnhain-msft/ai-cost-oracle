"""Tests for the estimator: corpus percentiles -> cost estimates."""

import pytest

import estimator
from stats_util import summarize


def _corpus(claude_requests: int = 100, copilot_requests: int = 100) -> dict:
    token_values = [float(i) for i in range(1, 101)]  # p50 = 50.5
    aic_values = [float(i) / 10 for i in range(1, 101)]  # p50 = 5.05
    tokens = {
        "input_tokens": summarize(token_values),
        "output_tokens": summarize(token_values),
        "cache_read_tokens": summarize([0.0] * 100),
        "cache_write_5m_tokens": summarize([0.0] * 100),
        "cache_write_1h_tokens": summarize([0.0] * 100),
    }
    return {
        "version": 2,
        "trained_at": "2026-10-24T00:00:00+00:00",
        "providers": {
            "claude": {
                "requests": claude_requests,
                "sessions": 10,
                "models": {
                    "claude-opus-5": {
                        "tokens_per_request": tokens,
                        "cost_usd_per_request": summarize(token_values),
                    }
                },
                "all_models": {
                    "tokens_per_request": tokens,
                    "cost_usd_per_request": summarize(token_values),
                },
                "requests_per_session": summarize([10.0] * 100),
                "cost_usd_per_session": summarize(token_values),
            },
            "copilot": {
                "requests": copilot_requests,
                "sessions": 10,
                "models": {
                    "claude-opus-5": {
                        "aic_per_request": summarize(aic_values),
                        "request_multiplier": summarize([1.0] * 100),
                    }
                },
                "all_models": {"aic_per_request": summarize(aic_values)},
                "requests_per_session": summarize([10.0] * 100),
                "aic_per_session": summarize(aic_values),
            },
        },
    }


@pytest.mark.unit
def test_claude_estimate_prices_tokens_at_model_rates():
    result = estimator.estimate_claude(
        _corpus(), "claude-opus-5", "add tests", "moderate", calibration=1.0
    )
    # p50 tokens = 50.5 in + 50.5 out at $5/$25 per MTok, x10 requests
    per_request = 50.5 * 5 / 1e6 + 50.5 * 25 / 1e6
    assert result.expected == pytest.approx(per_request * 10)
    assert result.unit == "USD"
    assert result.low < result.expected < result.high
    assert "claude-opus-5 history" in result.basis


@pytest.mark.unit
def test_claude_estimate_unseen_model_uses_baseline_tokens_and_new_rates():
    cheap = estimator.estimate_claude(
        _corpus(), "claude-haiku-4-5", "add tests", "moderate", calibration=1.0
    )
    pricey = estimator.estimate_claude(
        _corpus(), "claude-fable-5", "add tests", "moderate", calibration=1.0
    )
    assert "all-model baseline" in cheap.basis
    # Same token profile, different rates: fable 5 is 10x haiku on both axes.
    assert pricey.expected == pytest.approx(cheap.expected * 10)


@pytest.mark.unit
def test_copilot_estimate_uses_aic_distribution():
    result = estimator.estimate_copilot(
        _corpus(), "claude-opus-5", "fix bug", "moderate", calibration=1.0
    )
    assert result.unit == "AIC"
    assert result.expected == pytest.approx(5.05 * 10)


@pytest.mark.unit
def test_calibration_scales_linearly():
    base = estimator.estimate_copilot(
        _corpus(), "claude-opus-5", "", "moderate", calibration=1.0
    )
    scaled = estimator.estimate_copilot(
        _corpus(), "claude-opus-5", "", "moderate", calibration=1.5
    )
    assert scaled.expected == pytest.approx(base.expected * 1.5)


@pytest.mark.unit
def test_explicit_request_count_overrides_tier():
    result = estimator.estimate_claude(
        _corpus(), "claude-opus-5", "", "epic", calibration=1.0, n_requests=1
    )
    assert result.n_requests == 1


@pytest.mark.unit
def test_complexity_tiers_are_monotonic():
    costs = [
        estimator.estimate_copilot(
            _corpus(), "claude-opus-5", "", tier, calibration=1.0, n_requests=1
        ).expected
        for tier in ("quick", "simple", "moderate", "complex", "epic")
    ]
    assert costs == sorted(costs)


@pytest.mark.unit
def test_empty_corpus_raises():
    empty = _corpus()
    empty["providers"]["claude"]["requests"] = 0
    with pytest.raises(ValueError, match="no session history"):
        estimator.estimate_claude(empty, "claude-opus-5", "", "moderate", 1.0)


@pytest.mark.unit
def test_invalid_request_count_raises():
    with pytest.raises(ValueError, match="positive"):
        estimator.estimate_claude(
            _corpus(), "claude-opus-5", "", "moderate", 1.0, n_requests=0
        )
