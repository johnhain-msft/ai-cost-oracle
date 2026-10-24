"""Pricing tables and cost math.

Claude costs are computed from tokens at published API rates (USD per
million tokens). Copilot costs are measured in AIC (AI credits) — the unit
Copilot's own session store records as ``total_nano_aiu`` — so no USD table
is needed: AIC spend is learned directly from session history.
"""

from __future__ import annotations

from dataclasses import dataclass

# Cache pricing relative to base input rate (standard Anthropic multipliers).
CACHE_READ_MULTIPLIER: float = 0.10
CACHE_WRITE_5M_MULTIPLIER: float = 1.25
CACHE_WRITE_1H_MULTIPLIER: float = 2.00

NANO_AIU_PER_AIC: int = 1_000_000_000


@dataclass(frozen=True)
class ModelPrice:
    """USD per million tokens for one Claude model."""

    model: str
    input_per_mtok: float
    output_per_mtok: float


# Published Claude API rates (USD / MTok), current as of 2026-10.
CLAUDE_PRICES: dict[str, ModelPrice] = {
    price.model: price
    for price in (
        ModelPrice("claude-fable-5", 10.00, 50.00),
        ModelPrice("claude-mythos-5", 10.00, 50.00),
        ModelPrice("claude-opus-5", 5.00, 25.00),
        ModelPrice("claude-opus-4-8", 5.00, 25.00),
        ModelPrice("claude-opus-4-7", 5.00, 25.00),
        ModelPrice("claude-opus-4-6", 5.00, 25.00),
        ModelPrice("claude-sonnet-5", 3.00, 15.00),
        ModelPrice("claude-sonnet-4-6", 3.00, 15.00),
        ModelPrice("claude-sonnet-4-5", 3.00, 15.00),
        ModelPrice("claude-haiku-4-5", 1.00, 5.00),
    )
}


@dataclass(frozen=True)
class TokenUsage:
    """Token counts for a single request."""

    input_tokens: float = 0
    output_tokens: float = 0
    cache_read_tokens: float = 0
    cache_write_5m_tokens: float = 0
    cache_write_1h_tokens: float = 0

    @property
    def total_tokens(self) -> float:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_write_5m_tokens
            + self.cache_write_1h_tokens
        )


def normalize_model(model: str) -> str:
    """Normalize model ids across providers (``claude-opus-4.8`` → ``-4-8``)."""
    return model.strip().lower().replace(".", "-")


def resolve_claude_price(model: str) -> ModelPrice:
    """Look up pricing for a Claude model, raising with guidance if unknown."""
    normalized = normalize_model(model)
    if normalized in CLAUDE_PRICES:
        return CLAUDE_PRICES[normalized]
    # Date-suffixed ids (claude-sonnet-4-5-20250929) map to the base id.
    for known, price in CLAUDE_PRICES.items():
        if normalized.startswith(known):
            return price
    known_ids = ", ".join(sorted(CLAUDE_PRICES))
    raise KeyError(f"No pricing for model '{model}'. Known models: {known_ids}")


def claude_request_cost_usd(model: str, usage: TokenUsage) -> float:
    """Exact USD cost of one Claude request at published rates."""
    price = resolve_claude_price(model)
    input_rate = price.input_per_mtok / 1_000_000
    output_rate = price.output_per_mtok / 1_000_000
    return (
        usage.input_tokens * input_rate
        + usage.output_tokens * output_rate
        + usage.cache_read_tokens * input_rate * CACHE_READ_MULTIPLIER
        + usage.cache_write_5m_tokens * input_rate * CACHE_WRITE_5M_MULTIPLIER
        + usage.cache_write_1h_tokens * input_rate * CACHE_WRITE_1H_MULTIPLIER
    )


def nano_aiu_to_aic(nano_aiu: float) -> float:
    """Convert Copilot's stored nano-AIU to AIC (AI credits)."""
    return nano_aiu / NANO_AIU_PER_AIC
