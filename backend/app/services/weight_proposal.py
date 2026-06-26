"""WeightProposal — structured candidate weight configurations.

V4.3.0 S8: Formalizes the proposal-only convention that learning_engine
already follows.  A WeightProposal must pass BacktestGate before it can
be approved for production.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class WeightProposal:
    """A candidate weight configuration proposed by the learning engine.

    Must pass BacktestGate validation before approval_status can become
    'approved'.  PredictionEngine must ignore unapproved proposals.
    """

    proposal_id: str
    base_weight_config_id: str
    candidate_weights: dict[str, float]  # {component_name: new_weight}

    # Context
    affected_context: str = ""
    reason: str = ""
    evidence_match_ids: list[str] = field(default_factory=list)
    sample_size: int = 0

    # Gate metrics (populated by BacktestGate)
    paired_logloss_delta: float | None = None
    paired_brier_delta: float | None = None
    paired_rps_delta: float | None = None
    ece_delta: float | None = None
    passed_gate: bool = False

    # Lifecycle
    approval_status: str = "pending"  # pending | approved | rejected
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_by: str = "learning_engine"  # learning_engine | human | agent

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "base_weight_config_id": self.base_weight_config_id,
            "candidate_weights": self.candidate_weights,
            "reason": self.reason,
            "sample_size": self.sample_size,
            "paired_brier_delta": self.paired_brier_delta,
            "paired_logloss_delta": self.paired_logloss_delta,
            "paired_rps_delta": self.paired_rps_delta,
            "ece_delta": self.ece_delta,
            "passed_gate": self.passed_gate,
            "approval_status": self.approval_status,
            "created_at": self.created_at,
            "created_by": self.created_by,
        }
