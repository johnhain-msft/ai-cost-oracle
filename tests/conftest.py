"""Shared fixtures: make the skill's scripts importable and isolate state."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = (
    Path(__file__).resolve().parent.parent / "skills" / "cost-oracle" / "scripts"
)
sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture(autouse=True)
def isolated_oracle_home(tmp_path, monkeypatch):
    """Keep every test's corpus/calibration state inside tmp_path."""
    home = tmp_path / "oracle-home"
    monkeypatch.setenv("COST_ORACLE_HOME", str(home))
    return home
