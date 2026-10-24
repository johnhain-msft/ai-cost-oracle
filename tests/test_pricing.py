"""Unit tests for pricing math."""

import pytest

from pricing import (
    TokenUsage,
    claude_request_cost_usd,
    nano_aiu_to_aic,
    normalize_model,
    resolve_claude_price,
)


@pytest.mark.unit
def test_normalize_model_maps_dots_to_dashes():
    assert normalize_model("claude-opus-4.8") == "claude-opus-4-8"
    assert normalize_model("  Claude-Opus-5 ") == "claude-opus-5"


@pytest.mark.unit
def test_resolve_claude_price_handles_date_suffixes():
    assert resolve_claude_price("claude-sonnet-4-5-20250929").input_per_mtok == 3.00


@pytest.mark.unit
def test_resolve_claude_price_unknown_model_raises_with_guidance():
    with pytest.raises(KeyError, match="Known models"):
        resolve_claude_price("gpt-6.1-sol")


@pytest.mark.unit
def test_claude_request_cost_plain_tokens():
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
    assert claude_request_cost_usd("claude-opus-5", usage) == pytest.approx(30.00)


@pytest.mark.unit
def test_claude_request_cost_cache_multipliers():
    usage = TokenUsage(
        cache_read_tokens=1_000_000,  # 0.10x input rate
        cache_write_5m_tokens=1_000_000,  # 1.25x input rate
        cache_write_1h_tokens=1_000_000,  # 2.00x input rate
    )
    # Opus 5 input = $5/MTok -> 0.5 + 6.25 + 10.0
    assert claude_request_cost_usd("claude-opus-5", usage) == pytest.approx(16.75)


@pytest.mark.unit
def test_nano_aiu_to_aic():
    assert nano_aiu_to_aic(2_986_950_000) == pytest.approx(2.98695)
