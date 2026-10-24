"""Read GitHub Copilot CLI session history (~/.copilot/session-store.db).

Copilot records one row per model request in ``assistant_usage_events``,
including ``total_nano_aiu`` — the AIC (AI credit) spend for that request.
That column is the training signal for Copilot estimates.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from pricing import nano_aiu_to_aic, normalize_model

DEFAULT_COPILOT_DB = Path.home() / ".copilot" / "session-store.db"

_QUERY = """
SELECT session_id, model, input_tokens, output_tokens,
       cache_read_tokens, cache_write_tokens,
       total_nano_aiu, request_multiplier, created_at
FROM assistant_usage_events
WHERE total_nano_aiu IS NOT NULL
"""


@dataclass(frozen=True)
class CopilotRequest:
    """One billed Copilot request from the session store."""

    session_id: str
    model: str
    input_tokens: float
    output_tokens: float
    cache_read_tokens: float
    cache_write_tokens: float
    aic: float
    request_multiplier: float
    timestamp: str


def _row_to_request(row: sqlite3.Row) -> CopilotRequest:
    return CopilotRequest(
        session_id=row["session_id"],
        model=normalize_model(row["model"] or "unknown"),
        input_tokens=row["input_tokens"] or 0,
        output_tokens=row["output_tokens"] or 0,
        cache_read_tokens=row["cache_read_tokens"] or 0,
        cache_write_tokens=row["cache_write_tokens"] or 0,
        aic=nano_aiu_to_aic(row["total_nano_aiu"]),
        request_multiplier=row["request_multiplier"] or 1.0,
        timestamp=row["created_at"] or "",
    )


def scan(copilot_db: Path | None = None) -> list[CopilotRequest]:
    """Read every usage event from the Copilot session store.

    The database is opened read-only so a live Copilot session is never
    disturbed. A missing database simply yields an empty corpus.
    """
    db_path = copilot_db or DEFAULT_COPILOT_DB
    if not db_path.is_file():
        return []
    uri = f"file:{db_path}?mode=ro&immutable=0"
    try:
        connection = sqlite3.connect(uri, uri=True, timeout=5.0)
    except sqlite3.Error as error:
        raise RuntimeError(f"Could not open Copilot session store: {error}") from error
    try:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(_QUERY).fetchall()
        return [_row_to_request(row) for row in rows]
    except sqlite3.Error as error:
        raise RuntimeError(f"Could not read Copilot usage events: {error}") from error
    finally:
        connection.close()
