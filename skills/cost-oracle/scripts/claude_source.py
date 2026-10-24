"""Read Claude Code session history (~/.claude/projects/*/*.jsonl).

Every assistant turn in a transcript carries a ``message.usage`` block with
exact token counts. Those tokens, priced at published API rates, are the
training signal for Claude estimates.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pricing import TokenUsage, claude_request_cost_usd, normalize_model

DEFAULT_CLAUDE_DIR = Path.home() / ".claude" / "projects"


@dataclass(frozen=True)
class ClaudeRequest:
    """One billed Claude API request reconstructed from a transcript."""

    session_id: str
    model: str
    usage: TokenUsage
    cost_usd: float
    timestamp: str


def _parse_usage(raw: dict) -> TokenUsage:
    cache_creation = raw.get("cache_creation") or {}
    write_5m = cache_creation.get("ephemeral_5m_input_tokens")
    write_1h = cache_creation.get("ephemeral_1h_input_tokens")
    if write_5m is None and write_1h is None:
        # Older transcripts only expose the combined figure; treat as 5m.
        write_5m = raw.get("cache_creation_input_tokens", 0)
        write_1h = 0
    return TokenUsage(
        input_tokens=raw.get("input_tokens", 0) or 0,
        output_tokens=raw.get("output_tokens", 0) or 0,
        cache_read_tokens=raw.get("cache_read_input_tokens", 0) or 0,
        cache_write_5m_tokens=write_5m or 0,
        cache_write_1h_tokens=write_1h or 0,
    )


def _iter_transcript(path: Path) -> list[ClaudeRequest]:
    """Parse one transcript, deduplicating streamed updates per request id."""
    by_request: dict[str, ClaudeRequest] = {}
    anonymous: list[ClaudeRequest] = []
    session_id = path.stem
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("type") != "assistant":
                continue
            message = record.get("message") or {}
            raw_usage = message.get("usage")
            model = message.get("model")
            if not raw_usage or not model or "<synthetic>" in model:
                continue
            usage = _parse_usage(raw_usage)
            if usage.total_tokens <= 0:
                continue
            try:
                cost = claude_request_cost_usd(model, usage)
            except KeyError:
                continue  # unknown/experimental model: skip rather than guess
            request = ClaudeRequest(
                session_id=session_id,
                model=normalize_model(model),
                usage=usage,
                cost_usd=cost,
                timestamp=record.get("timestamp", ""),
            )
            key = record.get("requestId") or message.get("id")
            if key:
                by_request[key] = request  # last write wins: final usage totals
            else:
                anonymous.append(request)
    return list(by_request.values()) + anonymous


def scan(claude_dir: Path | None = None) -> list[ClaudeRequest]:
    """Scan every project transcript under the Claude Code home directory."""
    root = claude_dir or DEFAULT_CLAUDE_DIR
    if not root.is_dir():
        return []
    requests: list[ClaudeRequest] = []
    for transcript in sorted(root.glob("*/*.jsonl")):
        try:
            requests.extend(_iter_transcript(transcript))
        except OSError:
            continue  # unreadable file: skip, never abort the whole scan
    return requests
