"""Test fact-check audit for team tournament status."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Ensure the backend module is importable
BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from scripts.audit_team_facts import (
    load_team_statuses,
    scan_text,
    check_report_text,
)


@pytest.fixture
def team_statuses() -> dict:
    """Load the real team tournament status data for testing."""
    # Look for the data file relative to the backend directory
    data_candidates = [
        BACKEND_ROOT.parent / "data" / "team_tournament_status.json",
        BACKEND_ROOT / "data" / "team_tournament_status.json",
    ]
    data_path = None
    for candidate in data_candidates:
        if candidate.exists():
            data_path = candidate
            break
    if data_path is None:
        pytest.skip("team_tournament_status.json not found")
    statuses = load_team_statuses(data_path)
    if statuses is None or len(statuses) == 0:
        pytest.skip("No team status data loaded")
    return statuses


# ── Negative tests: wrong texts about qualified teams must be caught ──


def test_iraq_qualified_status_blocks_wrong_text(team_statuses):
    """Iraq is qualified; text implying they are still qualifying must fail."""
    iraq = team_statuses.get("Iraq")
    if iraq is None:
        pytest.skip("Iraq not in team status data")
    assert iraq["status"] == "qualified", (
        "Precondition: Iraq should be 'qualified' in test data"
    )

    # This phrase is in FORBIDDEN_PHRASES_IF_QUALIFIED and should be caught
    bad_text = "Iraq 仍处于世界杯预选赛周期，仍在为世界杯资格而战。"

    violations = check_report_text(bad_text, {"Iraq": iraq})
    assert len(violations) > 0, (
        "Expected FACT_CHECK_FAILED for Iraq qualified team with forbidden text"
    )
    assert violations[0]["team"] == "Iraq"
    assert violations[0]["status"] == "qualified"


def test_spain_qualified_status_blocks_wrong_text(team_statuses):
    """Spain is qualified; text implying they are still qualifying must fail."""
    spain = team_statuses.get("Spain")
    if spain is None:
        pytest.skip("Spain not in team status data")
    assert spain["status"] == "qualified", (
        "Precondition: Spain should be 'qualified' in test data"
    )

    # This phrase is in FORBIDDEN_PHRASES_IF_QUALIFIED and should be caught
    bad_text = "Spain 仍在预选赛阶段，还处于世界杯预选赛周期中。"

    violations = check_report_text(bad_text, {"Spain": spain})
    assert len(violations) > 0, (
        "Expected FACT_CHECK_FAILED for Spain qualified team with forbidden text"
    )
    assert violations[0]["team"] == "Spain"
    assert violations[0]["status"] == "qualified"


# ── Positive test: correct text about qualified teams passes ──


def test_correct_report_passes_fact_check(team_statuses):
    """A report that correctly describes Spain and Iraq as qualified should pass."""
    iraq = team_statuses.get("Iraq")
    spain = team_statuses.get("Spain")
    if iraq is None or spain is None:
        pytest.skip("Iraq or Spain not in team status data")
    assert iraq["status"] == "qualified"
    assert spain["status"] == "qualified"

    correct_text = (
        "Spain 和 Iraq 均已成功晋级2026年世界杯决赛圈。"
        "Spain 在 UEFA Group E 中以小组第一身份出线，"
        "Iraq 通过附加赛击败 Bolivia 获得世界杯门票。"
        "两支球队将在世界杯小组赛中亮相。"
    )

    teams_to_check = {"Iraq": iraq, "Spain": spain}
    violations = check_report_text(correct_text, teams_to_check)
    assert len(violations) == 0, (
        f"Expected no violations for correct report, got: {violations}"
    )
