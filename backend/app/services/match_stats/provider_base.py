"""Match statistics provider abstract base class."""
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class RawMatchStats:
    """Raw match statistics from a provider before normalization."""
    match_id: int
    provider: str
    provider_match_id: Optional[str] = None
    source_url: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    fetched_at: Optional[str] = None


@dataclass
class TeamMatchStats:
    """Normalized per-team match statistics (cleaned, validated)."""
    match_id: int
    team_name: str
    side: str  # 'home' or 'away'
    provider: str
    # Offensive
    goals: Optional[int] = None
    xg: Optional[float] = None
    shots_total: Optional[int] = None
    shots_on_target: Optional[int] = None
    shots_inside_box: Optional[int] = None
    big_chances: Optional[int] = None
    corners: Optional[int] = None
    # Possession & passing
    possession_pct: Optional[float] = None
    passes_attempted: Optional[int] = None
    pass_accuracy_pct: Optional[float] = None
    final_third_entries: Optional[int] = None
    # Defensive
    tackles: Optional[int] = None
    interceptions: Optional[int] = None
    clearances: Optional[int] = None
    fouls: Optional[int] = None
    yellow_cards: Optional[int] = None
    red_cards: Optional[int] = None
    # Goalkeeper
    saves: Optional[int] = None
    # Special events
    penalties_awarded: int = 0
    penalties_scored: int = 0
    own_goals: int = 0
    # Data quality
    data_quality_score: float = 0.0


class MatchStatsProvider:
    """Abstract base for match statistics data providers."""
    provider_name: str = "base"

    def fetch_match_stats(self, match_id: int, home_team: str, away_team: str) -> RawMatchStats:
        """Fetch raw match statistics for a match."""
        raise NotImplementedError

    def supports_xg(self) -> bool:
        """Does this provider return xG data?"""
        return False

    def supports_possession(self) -> bool:
        """Does this provider return possession data?"""
        return False
