"""ko_draw_guard.py — Post-Calibration Knockout Draw Guard.

Warns when a knockout-stage prediction has an implausibly low draw
probability after calibration.  This is a *diagnostic* guard (Phase 1:
warn-only) — it does NOT alter probabilities.  A Bayesian offset model
may be added in Phase 2 after accumulating enough KO samples.

Background
----------
The current pipeline executes draw-floor enforcement *before* Isotonic
calibration:

    Step 13.4: enforce_draw_floor(probs)  → draw >= 12%
    Step 13.5: calibrator.calibrate(probs) → may suppress draw again

If the calibrator learned from historical data where knockout draws were
under-represented, it can re-suppress the draw probability.  This was
observed in NED-MAR and GER-PAR post-match reviews.

Trigger conditions
------------------
All of the following must be true:

1. ``is_knockout == True``
2. ``draw_prob < 0.22``
3. At least one risk factor:
   - ``|elo_gap| < 50`` (teams are closely matched)
   - ``total_xg < 2.35`` (low-scoring match expected)
   - ``market_draw >= 0.25`` (market disagrees with model)
   - ``model_disagreement == True`` (components diverge)

Usage::

    from app.core.ko_draw_guard import check_ko_draw_guard

    guard_result = check_ko_draw_guard(
        draw_prob=0.18,
        is_knockout=True,
        elo_gap=30,
        total_xg=2.1,
        market_draw_prob=0.26,
    )
    if guard_result["triggered"]:
        logger.warning("KO draw guard triggered: %s", guard_result["reason"])
"""
from __future__ import annotations

from typing import Any

# ── Feature flag ──
KO_DRAW_GUARD_ENABLED = True

# ── Thresholds ──
KO_DRAW_FLOOR_WARNING = 0.22       # draw below this triggers review
ELO_GAP_CLOSE_THRESHOLD = 50       # |gap| below this is "close match"
TOTAL_XG_LOW_THRESHOLD = 2.35      # total xG below this is "low scoring"
MARKET_DRAW_DISAGREEMENT = 0.25    # market draw >= this indicates disagreement

# Knockout stage names (case-insensitive prefix match)
KO_STAGE_PREFIXES = (
    "round of 32", "round of 16", "round of 8",
    "quarter-final", "quarterfinal",
    "semi-final", "semifinal",
    "final", "third place",
)


def _is_ko_stage(stage: str | None) -> bool:
    """Return True if *stage* looks like a knockout round."""
    if not stage:
        return False
    stage_lower = stage.strip().lower()
    return any(stage_lower.startswith(prefix) for prefix in KO_STAGE_PREFIXES)


def check_ko_draw_guard(
    *,
    draw_prob: float,
    is_knockout: bool = False,
    stage: str | None = None,
    elo_gap: float | None = None,
    total_xg: float | None = None,
    market_draw_prob: float | None = None,
    model_disagreement: bool = False,
) -> dict[str, Any]:
    """Check whether a knockout prediction may be underestimating the draw.

    Returns a dict with keys:
        - ``checked``: bool (always True if guard ran)
        - ``triggered``: bool
        - ``reason``: str (empty if not triggered)
        - ``risk_factors``: list[str]
        - ``action``: str — always ``"warn_only"`` in Phase 1
    """
    if not KO_DRAW_GUARD_ENABLED:
        return {
            "checked": False,
            "triggered": False,
            "reason": "guard disabled",
            "risk_factors": [],
            "action": "none",
        }

    # Resolve knockout status from stage name if not explicitly set
    if not is_knockout and stage:
        is_knockout = _is_ko_stage(stage)

    if not is_knockout:
        return {
            "checked": True,
            "triggered": False,
            "reason": "not a knockout match",
            "risk_factors": [],
            "action": "none",
        }

    if draw_prob >= KO_DRAW_FLOOR_WARNING:
        return {
            "checked": True,
            "triggered": False,
            "reason": f"draw_prob ({draw_prob:.3f}) >= floor ({KO_DRAW_FLOOR_WARNING})",
            "risk_factors": [],
            "action": "none",
        }

    # ── Evaluate risk factors ──
    risk_factors: list[str] = []

    if elo_gap is not None and abs(elo_gap) < ELO_GAP_CLOSE_THRESHOLD:
        risk_factors.append(
            f"close Elo gap ({abs(elo_gap):.0f} < {ELO_GAP_CLOSE_THRESHOLD})"
        )

    if total_xg is not None and total_xg < TOTAL_XG_LOW_THRESHOLD:
        risk_factors.append(
            f"low total xG ({total_xg:.2f} < {TOTAL_XG_LOW_THRESHOLD})"
        )

    if market_draw_prob is not None and market_draw_prob >= MARKET_DRAW_DISAGREEMENT:
        risk_factors.append(
            f"market draw higher ({market_draw_prob:.3f} >= {MARKET_DRAW_DISAGREEMENT})"
        )

    if model_disagreement:
        risk_factors.append("high model disagreement")

    if not risk_factors:
        return {
            "checked": True,
            "triggered": False,
            "reason": (
                f"draw_prob ({draw_prob:.3f}) < floor but no risk factors present"
            ),
            "risk_factors": [],
            "action": "none",
        }

    return {
        "checked": True,
        "triggered": True,
        "reason": (
            f"KO draw {draw_prob:.1%} below {KO_DRAW_FLOOR_WARNING:.0%} with "
            f"risk factors: {', '.join(risk_factors)}"
        ),
        "risk_factors": risk_factors,
        "action": "warn_only",
    }
