"""ModelRegistry — track model versions, weights, and data provenance.

Every prediction_snapshot can reference a registry entry to answer:
  "Which model version, weight config, training data, and calibration
   produced this prediction?"

Design: Lightweight — uses a JSONLines file for portability, plus a DB table
for queryability. No heavy dependency.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Registry file location
REGISTRY_DIR = Path(__file__).resolve().parent.parent.parent / "model_artifacts"
REGISTRY_FILE = REGISTRY_DIR / "model_registry.jsonl"


@dataclass
class ModelRegistryEntry:
    """A single entry in the model registry — immutable once created."""

    model_name: str  # "DixonColesModel", "TabularMatchEnhancer", etc.
    model_version: str  # Semantic version of the model code
    weight_config_version: str  # Version from WeightConfig
    feature_version: str = "1.0"  # Feature engineering version
    training_data_hash: str = ""  # MD5 of (n_rows, date_range, team_count)
    training_start_date: str = ""
    training_end_date: str = ""
    calibration_version: str = ""
    active: bool = True
    notes: str = ""
    registry_id: str = ""
    created_at: str = ""

    def __post_init__(self):
        if not self.registry_id:
            # Deterministic ID from key fields
            key = (
                f"{self.model_name}:{self.model_version}:"
                f"{self.weight_config_version}:{self.training_data_hash}"
            )
            self.registry_id = hashlib.md5(key.encode()).hexdigest()[:12]
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "registry_id": self.registry_id,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "weight_config_version": self.weight_config_version,
            "feature_version": self.feature_version,
            "training_data_hash": self.training_data_hash,
            "training_start_date": self.training_start_date,
            "training_end_date": self.training_end_date,
            "calibration_version": self.calibration_version,
            "active": self.active,
            "notes": self.notes,
            "created_at": self.created_at,
        }


class ModelRegistry:
    """Manage model version registry — append-only JSONLines + optional DB.

    Usage:
        registry = ModelRegistry()
        entry = registry.register(
            model_name="DixonColesModel",
            model_version="2.0",
            weight_config_version="2.0",
            training_data_hash="abc123",
            training_start_date="2015-01-01",
            training_end_date="2026-06-03",
            notes="Vectorized NLL + auto-optimized weights",
        )
        registry_id = entry.registry_id
    """

    def __init__(self) -> None:
        REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
        self._entries: list[ModelRegistryEntry] | None = None

    def register(
        self,
        model_name: str,
        model_version: str,
        weight_config_version: str,
        training_data_hash: str = "",
        training_start_date: str = "",
        training_end_date: str = "",
        calibration_version: str = "",
        feature_version: str = "1.0",
        notes: str = "",
    ) -> ModelRegistryEntry:
        """Register a new model configuration.

        If an identical entry already exists, returns the existing one (idempotent).
        """
        entry = ModelRegistryEntry(
            model_name=model_name,
            model_version=model_version,
            weight_config_version=weight_config_version,
            feature_version=feature_version,
            training_data_hash=training_data_hash,
            training_start_date=training_start_date,
            training_end_date=training_end_date,
            calibration_version=calibration_version,
            notes=notes,
        )

        # Check for existing identical entry
        existing = self._find_existing(entry)
        if existing:
            logger.debug(f"Registry entry already exists: {existing.registry_id}")
            return existing

        # Append to JSONLines file
        with open(REGISTRY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")

        # Invalidate cache
        self._entries = None

        logger.info(f"Registered model: {entry.registry_id} — {model_name} v{model_version}")
        return entry

    def list_entries(self) -> list[ModelRegistryEntry]:
        """List all registry entries."""
        if self._entries is not None:
            return self._entries

        entries = []
        if REGISTRY_FILE.exists():
            with open(REGISTRY_FILE, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            data = json.loads(line)
                            entries.append(ModelRegistryEntry(
                                registry_id=data.get("registry_id", ""),
                                model_name=data.get("model_name", ""),
                                model_version=data.get("model_version", ""),
                                weight_config_version=data.get("weight_config_version", ""),
                                feature_version=data.get("feature_version", "1.0"),
                                training_data_hash=data.get("training_data_hash", ""),
                                training_start_date=data.get("training_start_date", ""),
                                training_end_date=data.get("training_end_date", ""),
                                calibration_version=data.get("calibration_version", ""),
                                active=data.get("active", True),
                                notes=data.get("notes", ""),
                                created_at=data.get("created_at", ""),
                            ))
                        except (json.JSONDecodeError, KeyError) as exc:
                            logger.debug("Skipping malformed registry entry: %s", exc)
        self._entries = entries
        return entries

    def get_latest(self, model_name: str) -> ModelRegistryEntry | None:
        """Get the latest active entry for a given model."""
        entries = [
            e for e in self.list_entries()
            if e.model_name == model_name and e.active
        ]
        if not entries:
            return None
        return sorted(entries, key=lambda e: e.created_at, reverse=True)[0]

    def _find_existing(self, entry: ModelRegistryEntry) -> ModelRegistryEntry | None:
        """Check if an identical entry already exists."""
        for e in self.list_entries():
            if e.registry_id == entry.registry_id:
                return e
        return None


# ── Convenience ──

def get_current_registry_id(
    model_name: str = "DixonColesModel",
    model_version: str = "2.0",
    weight_config_version: str = "2.0",
    training_data_hash: str = "",
) -> str:
    """Get or create a registry entry and return its ID.

    This is the quick entry point for attaching registry metadata
    to prediction snapshots.
    """
    registry = ModelRegistry()
    entry = registry.register(
        model_name=model_name,
        model_version=model_version,
        weight_config_version=weight_config_version,
        training_data_hash=training_data_hash,
        notes=f"Auto-registered at {datetime.now(timezone.utc).isoformat()}",
    )
    return entry.registry_id
