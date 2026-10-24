"""Tests for the training round: parsing session history into a corpus."""

import json
import sqlite3
from pathlib import Path

import pytest

import claude_source
import copilot_source
import corpus
from stats_util import percentile, summarize


def _write_transcript(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")


def _assistant_record(request_id: str, model: str, output_tokens: int) -> dict:
    return {
        "type": "assistant",
        "requestId": request_id,
        "timestamp": "2026-10-01T00:00:00Z",
        "message": {
            "model": model,
            "usage": {
                "input_tokens": 100,
                "output_tokens": output_tokens,
                "cache_read_input_tokens": 1000,
                "cache_creation_input_tokens": 500,
                "cache_creation": {
                    "ephemeral_5m_input_tokens": 500,
                    "ephemeral_1h_input_tokens": 0,
                },
            },
        },
    }


@pytest.fixture
def claude_dir(tmp_path) -> Path:
    root = tmp_path / "projects"
    _write_transcript(
        root / "proj-a" / "session-1.jsonl",
        [
            {"type": "user", "message": {"content": "hi"}},
            _assistant_record("req-1", "claude-opus-5", 200),
            _assistant_record("req-1", "claude-opus-5", 400),  # streamed update
            _assistant_record("req-2", "claude-haiku-4-5", 50),
            {"type": "assistant", "message": {"model": "<synthetic>", "usage": {}}},
            "not json at all",
        ],
    )
    # The invalid line must be raw text, not JSON-encoded.
    raw = (root / "proj-a" / "session-1.jsonl").read_text()
    (root / "proj-a" / "session-1.jsonl").write_text(
        raw.replace('"not json at all"', "not json at all")
    )
    return root


@pytest.fixture
def copilot_db(tmp_path) -> Path:
    db = tmp_path / "session-store.db"
    connection = sqlite3.connect(db)
    connection.execute(
        """CREATE TABLE assistant_usage_events (
            session_id TEXT, model TEXT, input_tokens INTEGER,
            output_tokens INTEGER, cache_read_tokens INTEGER,
            cache_write_tokens INTEGER, total_nano_aiu INTEGER,
            request_multiplier REAL, created_at TEXT)"""
    )
    rows = [
        ("s1", "claude-opus-5", 100, 50, 0, 0, 2_000_000_000, 1.0, "2026-10-01"),
        ("s1", "gpt-6.1-sol", 200, 80, 10, 5, 3_000_000_000, 1.0, "2026-10-01"),
        ("s2", "claude-opus-5", 300, 90, 0, 0, 1_000_000_000, 1.0, "2026-10-02"),
        ("s2", "claude-opus-5", 300, 90, 0, 0, None, 1.0, "2026-10-02"),  # skipped
    ]
    connection.executemany("INSERT INTO assistant_usage_events VALUES (?,?,?,?,?,?,?,?,?)", rows)
    connection.commit()
    connection.close()
    return db


@pytest.mark.unit
def test_percentile_interpolates():
    assert percentile([1.0, 2.0, 3.0, 4.0], 0.5) == pytest.approx(2.5)
    assert summarize([])["count"] == 0


@pytest.mark.unit
def test_claude_scan_dedupes_streamed_updates(claude_dir):
    requests = claude_source.scan(claude_dir)
    assert len(requests) == 2  # req-1 deduped, synthetic + bad line skipped
    opus = next(r for r in requests if r.model == "claude-opus-5")
    assert opus.usage.output_tokens == 400  # last streamed update wins
    assert opus.cost_usd > 0


@pytest.mark.unit
def test_claude_scan_missing_dir_returns_empty(tmp_path):
    assert claude_source.scan(tmp_path / "nope") == []


@pytest.mark.unit
def test_copilot_scan_reads_aic(copilot_db):
    requests = copilot_source.scan(copilot_db)
    assert len(requests) == 3  # NULL aiu row skipped
    assert requests[0].aic == pytest.approx(2.0)
    assert {r.model for r in requests} == {"claude-opus-5", "gpt-6-1-sol"}


@pytest.mark.unit
def test_copilot_scan_missing_db_returns_empty(tmp_path):
    assert copilot_source.scan(tmp_path / "missing.db") == []


@pytest.mark.integration
def test_build_save_load_roundtrip(claude_dir, copilot_db):
    built = corpus.build(claude_dir=claude_dir, copilot_db=copilot_db)
    corpus.save(built)
    loaded = corpus.load()

    claude_section = loaded["providers"]["claude"]
    assert claude_section["requests"] == 2
    assert claude_section["sessions"] == 1
    assert "claude-opus-5" in claude_section["models"]

    copilot_section = loaded["providers"]["copilot"]
    assert copilot_section["requests"] == 3
    assert copilot_section["sessions"] == 2
    assert copilot_section["all_models"]["aic_per_request"]["count"] == 3


@pytest.mark.unit
def test_session_baselines_exclude_background_noise():
    per_session = {
        "bg1": [1.0],  # single-request background sessions
        "bg2": [1.0],
        "task": [1.0] * 20,  # one real working session
    }
    kept = corpus._interactive(per_session)
    assert kept == [[1.0] * 20]


@pytest.mark.unit
def test_session_baselines_fall_back_when_all_sessions_small():
    per_session = {"a": [1.0], "b": [2.0]}
    assert len(corpus._interactive(per_session)) == 2


@pytest.mark.unit
def test_load_without_training_raises():
    with pytest.raises(FileNotFoundError, match="cost-oracle train"):
        corpus.load()
