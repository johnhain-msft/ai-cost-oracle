"""Tests for feedback recording and calibration."""

import pytest

import feedback
from estimator import Estimate


def _estimate(estimate_id: str = "abc12345", expected: float = 10.0) -> Estimate:
    return Estimate(
        estimate_id=estimate_id,
        created_at="2026-10-24T00:00:00+00:00",
        provider="claude",
        model="claude-opus-5",
        task="demo",
        complexity="moderate",
        n_requests=10,
        unit="USD",
        expected=expected,
        low=5.0,
        high=20.0,
        calibration=1.0,
        basis="test",
    )


@pytest.mark.unit
def test_record_and_find_estimate():
    feedback.record_estimate(_estimate())
    found = feedback.find_estimate("abc12345")
    assert found["expected"] == 10.0


@pytest.mark.unit
def test_find_missing_estimate_raises():
    with pytest.raises(KeyError, match="abc99999"):
        feedback.find_estimate("abc99999")


@pytest.mark.unit
def test_feedback_moves_calibration_toward_actual():
    feedback.record_estimate(_estimate())
    report = feedback.apply_feedback("abc12345", actual=20.0)  # 2x under-estimate
    assert report["factor_before"] == pytest.approx(1.0)
    assert 1.0 < report["factor_after"] < 2.0  # EWMA pulls up, not all the way
    assert report["error_pct"] == pytest.approx(-50.0)


@pytest.mark.unit
def test_feedback_converges_with_repeats():
    factor = 1.0
    for i in range(12):
        feedback.record_estimate(_estimate(estimate_id=f"conv{i:04d}"))
        report = feedback.apply_feedback(f"conv{i:04d}", actual=20.0)
        factor = report["factor_after"]
    assert factor == pytest.approx(2.0, rel=0.05)


@pytest.mark.unit
def test_calibration_is_clamped():
    feedback.record_estimate(_estimate(expected=0.01))
    report = feedback.apply_feedback("abc12345", actual=1000.0)
    assert report["factor_after"] <= feedback.CALIBRATION_CEILING


@pytest.mark.unit
def test_invalid_actual_raises():
    feedback.record_estimate(_estimate())
    with pytest.raises(ValueError, match="positive"):
        feedback.apply_feedback("abc12345", actual=0)


@pytest.mark.unit
def test_accuracy_report_tracks_mape():
    feedback.record_estimate(_estimate())
    feedback.apply_feedback("abc12345", actual=8.0)  # 25% over
    report = feedback.accuracy_report("claude")
    assert report["samples"] == 1
    assert report["mape_pct"] == pytest.approx(25.0)
    assert feedback.accuracy_report("copilot") == {"provider": "copilot", "samples": 0}
