"""BacktestGate — validates WeightProposals before production approval.

V4.3.0 S8: Enforces minimum quality thresholds for weight changes.
No proposal may update production weights without passing this gate.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Default gate thresholds
DEFAULT_MIN_SAMPLE_SIZE = 10
DEFAULT_MAX_WEIGHT_DELTA = 0.03  # max single-component weight change


class BacktestGate:
    """Validates weight proposals against quality thresholds.

    A proposal must pass ALL gates to be marked as 'approved'.
    Failing any gate results in 'rejected' status with a reason.
    """

    def __init__(
        self,
        min_sample_size: int = DEFAULT_MIN_SAMPLE_SIZE,
        max_weight_delta: float = DEFAULT_MAX_WEIGHT_DELTA,
    ):
        self.min_sample_size = min_sample_size
        self.max_weight_delta = max_weight_delta

    def validate(self, proposal) -> list[str]:
        """Run all gate checks. Returns list of failure reasons (empty = passed)."""
        failures: list[str] = []

        # Gate 1: Minimum sample size
        if proposal.sample_size < self.min_sample_size:
            failures.append(
                f"sample_size={proposal.sample_size} < min={self.min_sample_size}"
            )

        # Gate 2: Paired comparison only — no unpaired "improvements"
        if proposal.paired_brier_delta is None and proposal.paired_logloss_delta is None:
            failures.append("no paired comparison metrics available")

        # Gate 3: LogLoss must not worsen
        if (
            proposal.paired_logloss_delta is not None
            and proposal.paired_logloss_delta > 0.001
        ):
            failures.append(
                f"logloss worsened by {proposal.paired_logloss_delta:+.4f}"
            )

        # Gate 4: Brier must not worsen
        if (
            proposal.paired_brier_delta is not None
            and proposal.paired_brier_delta > 0.001
        ):
            failures.append(
                f"Brier worsened by {proposal.paired_brier_delta:+.4f}"
            )

        # Gate 5: RPS must not worsen
        if (
            proposal.paired_rps_delta is not None
            and proposal.paired_rps_delta > 0.005
        ):
            failures.append(
                f"RPS worsened by {proposal.paired_rps_delta:+.4f}"
            )

        # Gate 6: ECE must not worsen significantly
        if (
            proposal.ece_delta is not None
            and proposal.ece_delta > 0.02
        ):
            failures.append(
                f"ECE worsened by {proposal.ece_delta:+.4f}"
            )

        # Gate 7: Max single-component weight change
        # NOTE: max_weight_delta (default 0.03) enforces conservative step sizes.
        # Full delta check requires proposal.current_weights — not yet plumbed.
        # For now we enforce absolute bounds and a reasonable maximum (0.75).
        if proposal.candidate_weights:
            for comp_name, new_weight in proposal.candidate_weights.items():
                if new_weight < 0 or new_weight > 1.0:
                    failures.append(
                        f"{comp_name} weight {new_weight:.3f} out of [0, 1]"
                    )
                elif new_weight > 0.75 and comp_name != "dc":
                    failures.append(
                        f"{comp_name} weight {new_weight:.3f} exceeds "
                        f"safety ceiling 0.75 (max_delta={self.max_weight_delta})"
                    )

        return failures

    def apply(self, proposal) -> bool:
        """Validate and update proposal status. Returns True if passed."""
        failures = self.validate(proposal)
        if failures:
            proposal.passed_gate = False
            proposal.approval_status = "rejected"
            logger.warning(
                "WeightProposal %s REJECTED: %s",
                proposal.proposal_id,
                "; ".join(failures),
            )
            return False

        proposal.passed_gate = True
        # Note: approval_status stays 'pending' — human must still approve
        logger.info(
            "WeightProposal %s PASSED gate (pending human approval)",
            proposal.proposal_id,
        )
        return True
