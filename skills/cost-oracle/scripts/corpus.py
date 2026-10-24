"""The training round: build a baseline corpus from local session history.

The corpus stores distribution summaries (percentiles), never raw prompts or
conversation content — it is a statistical baseline, not a data export.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import claude_source
import copilot_source
from stats_util import summarize

CORPUS_VERSION = 2
MIN_MODEL_SAMPLES = 15  # below this, fall back to the all-model baseline
# Sessions with fewer requests than this are background noise (health checks,
# one-shot completions) and would drag the task-size baseline toward 1; they
# still count toward per-request cost stats, just not session-shape stats.
MIN_SESSION_REQUESTS = 3


def _interactive(per_session: dict[str, list[float]]) -> list[list[float]]:
    """Session cost lists large enough to represent a real task."""
    kept = [v for v in per_session.values() if len(v) >= MIN_SESSION_REQUESTS]
    return kept or list(per_session.values())


def oracle_home() -> Path:
    """State directory (override with COST_ORACLE_HOME for tests/CI)."""
    override = os.environ.get("COST_ORACLE_HOME")
    return Path(override) if override else Path.home() / ".cost-oracle"


def corpus_path() -> Path:
    return oracle_home() / "corpus.json"


def _token_summaries(usages: list[dict[str, float]]) -> dict[str, dict[str, float]]:
    fields = (
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_write_5m_tokens",
        "cache_write_1h_tokens",
    )
    return {field: summarize([u[field] for u in usages]) for field in fields}


def _build_claude_section(requests: list[claude_source.ClaudeRequest]) -> dict:
    by_model: dict[str, list[claude_source.ClaudeRequest]] = defaultdict(list)
    per_session: dict[str, list[float]] = defaultdict(list)
    for request in requests:
        by_model[request.model].append(request)
        per_session[request.session_id].append(request.cost_usd)

    def usage_dicts(
        batch: Iterable[claude_source.ClaudeRequest],
    ) -> list[dict[str, float]]:
        return [
            {
                "input_tokens": r.usage.input_tokens,
                "output_tokens": r.usage.output_tokens,
                "cache_read_tokens": r.usage.cache_read_tokens,
                "cache_write_5m_tokens": r.usage.cache_write_5m_tokens,
                "cache_write_1h_tokens": r.usage.cache_write_1h_tokens,
            }
            for r in batch
        ]

    models = {
        model: {
            "tokens_per_request": _token_summaries(usage_dicts(batch)),
            "cost_usd_per_request": summarize([r.cost_usd for r in batch]),
        }
        for model, batch in sorted(by_model.items())
    }
    return {
        "requests": len(requests),
        "sessions": len(per_session),
        "models": models,
        "all_models": {
            "tokens_per_request": _token_summaries(usage_dicts(requests)),
            "cost_usd_per_request": summarize([r.cost_usd for r in requests]),
        },
        "requests_per_session": summarize([float(len(v)) for v in _interactive(per_session)]),
        "cost_usd_per_session": summarize([sum(v) for v in _interactive(per_session)]),
    }


def _build_copilot_section(requests: list[copilot_source.CopilotRequest]) -> dict:
    by_model: dict[str, list[copilot_source.CopilotRequest]] = defaultdict(list)
    per_session: dict[str, list[float]] = defaultdict(list)
    for request in requests:
        by_model[request.model].append(request)
        per_session[request.session_id].append(request.aic)

    models = {
        model: {
            "aic_per_request": summarize([r.aic for r in batch]),
            "request_multiplier": summarize([r.request_multiplier for r in batch]),
        }
        for model, batch in sorted(by_model.items())
    }
    return {
        "requests": len(requests),
        "sessions": len(per_session),
        "models": models,
        "all_models": {"aic_per_request": summarize([r.aic for r in requests])},
        "requests_per_session": summarize([float(len(v)) for v in _interactive(per_session)]),
        "aic_per_session": summarize([sum(v) for v in _interactive(per_session)]),
    }


def build(
    claude_dir: Path | None = None,
    copilot_db: Path | None = None,
) -> dict:
    """Run the training round over both providers' local session history."""
    claude_requests = claude_source.scan(claude_dir)
    copilot_requests = copilot_source.scan(copilot_db)
    return {
        "version": CORPUS_VERSION,
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "providers": {
            "claude": _build_claude_section(claude_requests),
            "copilot": _build_copilot_section(copilot_requests),
        },
    }


def save(corpus: dict, path: Path | None = None) -> Path:
    target = path or corpus_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(corpus, indent=2), encoding="utf-8")
    return target


def load(path: Path | None = None) -> dict:
    source = path or corpus_path()
    if not source.is_file():
        raise FileNotFoundError(
            f"No corpus at {source}. Run the training round first: cost-oracle train"
        )
    corpus = json.loads(source.read_text(encoding="utf-8"))
    if corpus.get("version") != CORPUS_VERSION:
        raise ValueError(
            f"Corpus at {source} is version {corpus.get('version')}, "
            f"expected {CORPUS_VERSION}. Re-run: cost-oracle train"
        )
    return corpus
