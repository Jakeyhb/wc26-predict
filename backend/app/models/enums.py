from __future__ import annotations

from enum import StrEnum


class MatchStatus(StrEnum):
    SCHEDULED = "scheduled"
    LIVE = "live"
    FINISHED = "finished"
    POSTPONED = "postponed"
    CANCELLED = "cancelled"


class CompetitionType(StrEnum):
    NATIONAL = "national"
    CLUB = "club"
    CUP = "cup"


class TeamType(StrEnum):
    NATIONAL = "national"
    CLUB = "club"


class SignalType(StrEnum):
    INJURY = "injury"
    RETURN = "return"
    LINEUP_HINT = "lineup_hint"
    COACH_STATEMENT = "coach_statement"
    TRAINING = "training"
    TRAVEL = "travel"
    WEATHER = "weather"
    OTHER = "other"


class ImpactDirection(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    UNCERTAIN = "uncertain"


class ReviewStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class PredictionRunType(StrEnum):
    T_MINUS_24H = "t_minus_24h"
    T_MINUS_3H = "t_minus_3h"
    LINEUP_CONFIRMED = "lineup_confirmed"
    MANUAL = "manual"


class MatchResultCode(StrEnum):
    HOME = "H"
    DRAW = "D"
    AWAY = "A"


class SignalEvalLabel(StrEnum):
    ACCURATE = "accurate"
    MISLEADING = "misleading"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"
