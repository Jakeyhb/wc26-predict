"""ArtifactRegistry — manage model artifact bundles and component validation.

Each registry entry tracks a bundle of fitted models (Dixon-Coles, TabularEnhancer,
Elo, Pi-Rating, Weibull) keyed by team type (national, club). The registry JSON
lives at backend/artifacts/model_registry.json and serves as the single source
of truth for which artifact versions are currently active.

Typical usage:
    registry = load_registry()
    bundle = get_active_bundle("national")
    if bundle:
        ok, missing = validate_bundle(bundle, mode="standard")
        if ok:
            logger.info("All required components ready")
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Registry file location — resolves to backend/artifacts/model_registry.json
REGISTRY_PATH = Path(__file__).resolve().parents[2] / "artifacts" / "model_registry.json"

# All known prediction modes and what they require.
# Each component listed in "requires" must have status "ready" for
# validate_bundle to return True.
REQUIRED_FOR_MODE: dict[str, list[str]] = {
    "baseline": ["dixon_coles"],
    "standard": ["dixon_coles", "tabular_enhancer", "elo"],
    "full": ["dixon_coles", "tabular_enhancer", "elo", "pi_rating"],
    "research-full": ["dixon_coles", "tabular_enhancer", "elo", "pi_rating"],
}


def load_registry() -> dict:
    """Load the model registry JSON file.

    Returns the parsed registry dict, or a minimal default structure
    if the file does not exist or cannot be parsed.
    """
    if not REGISTRY_PATH.exists():
        logger.warning("Registry file not found at %s — returning empty registry", REGISTRY_PATH)
        return _empty_registry()

    try:
        with open(REGISTRY_PATH, encoding="utf-8") as f:
            registry: dict = json.load(f)
        logger.info(
            "Registry loaded: schema_version=%s, active teams=%s",
            registry.get("schema_version", "?"),
            list(registry.get("active", {})),
        )
        return registry
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to load registry: %s", exc)
        return _empty_registry()


def save_registry(registry: dict) -> None:
    """Persist the registry dict to the JSON file.

    Creates parent directories if they do not exist.
    """
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)
    logger.info("Registry saved to %s", REGISTRY_PATH)


def get_active_bundle(team_type: str = "national") -> dict | None:
    """Get the active bundle dict for a given team type.

    Parameters
    ----------
    team_type : str
        Key into registry["active"], typically "national" or "club".

    Returns
    -------
    dict | None
        The active bundle (with "data_fingerprint", "trained_at",
        "components", etc.) or None if not found.
    """
    registry = load_registry()
    return registry.get("active", {}).get(team_type)


def validate_bundle(bundle: dict, mode: str) -> tuple[bool, list[str]]:
    """Check whether a bundle has all components needed for a given mode.

    Parameters
    ----------
    bundle : dict
        A bundle dict from the registry (e.g. registry["active"]["national"]).
    mode : str
        Prediction mode — one of "baseline", "standard", "full", "research-full".

    Returns
    -------
    tuple[bool, list[str]]
        (ok, missing_components):
        - ok is True when every component required by *mode* has status "ready".
        - missing_components lists the component names that are required but not ready.
    """
    required = REQUIRED_FOR_MODE.get(mode, [])
    components = bundle.get("components", {})

    missing: list[str] = []
    for name in required:
        component = components.get(name, {})
        status = component.get("status", "missing")
        if status != "ready":
            missing.append(name)

    ok = len(missing) == 0
    if not ok:
        logger.warning(
            "Bundle validation failed for mode=%s: missing components=%s",
            mode,
            missing,
        )
    return (ok, missing)


# ── Internal helpers ──────────────────────────────────────


def _empty_registry() -> dict:
    """Return a minimal registry dict for when no file exists yet."""
    return {
        "schema_version": "1.0",
        "active": {},
    }
