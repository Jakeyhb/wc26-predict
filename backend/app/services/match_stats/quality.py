"""Match statistics data quality scorer.

Produces a 0.0-1.0 quality score for each team's stats, used to:
  - Gate which matches enter the learning pipeline
  - Weight the contribution of each match to parameter proposals
  - Flag data integrity issues (e.g. shots < shots_on_target)
"""

from typing import Dict, Optional


def compute_data_quality_score(stats: Dict, side: str = "home") -> float:
    """Compute a quality score (0.0-1.0) for a set of match team stats.

    The score starts at 1.0 and is penalized for:
      - Missing core fields (xg, shots_total, shots_on_target)
      - Logical inconsistencies (SoT > total shots)
      - Possession sum not ~100%
      - Negative or impossible values

    Args:
        stats: Dictionary of normalized team stats (canonical field names).
        side: 'home' or 'away' (for possession validation requires both).

    Returns:
        Quality score between 0.0 and 1.0.
    """
    score = 1.0

    # --- Missing core fields ---
    core_fields = ["shots_total", "shots_on_target"]
    bonus_fields = ["xg", "possession_pct", "passes_attempted", "corners", "saves"]
    required = core_fields + bonus_fields

    missing = [f for f in required if stats.get(f) is None]
    score -= 0.10 * len(missing)

    # --- Logical consistency checks ---
    shots_total = _safe_int(stats.get("shots_total"))
    shots_on_target = _safe_int(stats.get("shots_on_target"))

    if shots_total is not None and shots_total < 0:
        score -= 0.30
    if shots_on_target is not None and shots_on_target < 0:
        score -= 0.30
    if shots_total is not None and shots_on_target is not None:
        if shots_on_target > shots_total:
            score -= 0.25

    # xG should be non-negative
    xg = stats.get("xg")
    if xg is not None:
        try:
            if float(xg) < 0:
                score -= 0.30
        except (ValueError, TypeError):
            score -= 0.10

    # Goals should be non-negative
    goals = stats.get("goals")
    if goals is not None:
        try:
            if int(goals) < 0:
                score -= 0.20
        except (ValueError, TypeError):
            pass

    return max(0.0, min(1.0, score))


def validate_possession(home_pct: Optional[float], away_pct: Optional[float]) -> float:
    """Check that home + away possession approximates 100%.
    Returns a penalty factor (0.0-1.0) to multiply into quality score.
    """
    if home_pct is None or away_pct is None:
        return 1.0  # Cannot validate, pass through
    total = home_pct + away_pct
    delta = abs(total - 100)
    if delta <= 2:
        return 1.0
    elif delta <= 5:
        return 0.90
    elif delta <= 10:
        return 0.75
    else:
        return 0.50


def compute_source_consensus_score(
    primary_stats: Dict, secondary_stats: Optional[Dict], tolerance_pct: float = 0.20
) -> float:
    """Compare two sources for consistency on overlapping fields.

    Returns:
        1.0 if identical or no secondary, lower if discrepancies found.
    """
    if secondary_stats is None:
        return 0.85  # Single source — slightly penalized

    comparable_fields = ["shots_total", "shots_on_target", "goals", "corners", "fouls"]
    matches = 0
    total = 0
    for field in comparable_fields:
        v1 = primary_stats.get(field)
        v2 = secondary_stats.get(field)
        if v1 is not None and v2 is not None:
            total += 1
            try:
                if abs(float(v1) - float(v2)) <= tolerance_pct * max(abs(float(v1)), 1):
                    matches += 1
            except (ValueError, TypeError):
                pass

    if total == 0:
        return 0.85
    return 0.85 + 0.15 * (matches / total)


def _safe_int(value) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None
