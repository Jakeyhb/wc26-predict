#!/usr/bin/env python3
"""Walk-forward champion/challenger evaluation over stored predictions.

The script evaluates only predictions whose as_of_time/generated_at is not
after kickoff. It emits a structured report and a release-gate decision without
retraining models.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.evaluation_metrics import ThreeWayMetrics, evaluate_three_way


PROPER_METRICS = ("log_loss", "brier", "rps")


@dataclass
class Aggregate:
    n: int = 0
    brier: float = 0.0
    log_loss: float = 0.0
    rps: float = 0.0
    correct: int = 0

    def add(self, *, brier: float, log_loss: float, rps: float, correct: bool) -> None:
        self.n += 1
        self.brier += brier
        self.log_loss += log_loss
        self.rps += rps
        self.correct += int(correct)

    def add_metrics(self, metrics: ThreeWayMetrics) -> None:
        self.add(brier=metrics.brier, log_loss=metrics.log_loss, rps=metrics.rps, correct=metrics.correct)

    def merge(self, other: "Aggregate") -> None:
        self.n += other.n
        self.brier += other.brier
        self.log_loss += other.log_loss
        self.rps += other.rps
        self.correct += other.correct

    def averages(self) -> dict[str, float | int]:
        if self.n == 0:
            return {"n": 0, "log_loss": 0.0, "brier": 0.0, "rps": 0.0, "accuracy": 0.0}
        return {
            "n": self.n,
            "log_loss": self.log_loss / self.n,
            "brier": self.brier / self.n,
            "rps": self.rps / self.n,
            "accuracy": self.correct / self.n,
        }

    def row(self, label: str) -> str:
        if self.n == 0:
            return f"{label:42} n=0"
        avg = self.averages()
        return (
            f"{label:42} n={self.n:4d} "
            f"log_loss={avg['log_loss']:.4f} "
            f"brier={avg['brier']:.4f} "
            f"rps={avg['rps']:.4f} "
            f"acc={avg['accuracy']:.3f}"
        )


@dataclass(frozen=True)
class GateConfig:
    champion_label: str
    min_sample: int
    group_min_sample: int
    max_group_regression: float


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00").replace(" ", "T")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(text.split(".")[0])
        except ValueError:
            return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _horizon(as_of_time: datetime, kickoff: datetime) -> str:
    hours = (kickoff - as_of_time).total_seconds() / 3600
    if 18 <= hours <= 30:
        return "t_minus_24h"
    if 3 <= hours < 9:
        return "t_minus_6h"
    if 0 <= hours < 3:
        return "t_minus_90m"
    if hours >= 0:
        return "other_prematch"
    return "after_kickoff"


def _load_prediction_run_rows(conn: sqlite3.Connection, limit: int | None) -> list[sqlite3.Row]:
    query = """
        SELECT
            'prediction_runs' AS source,
            pr.id,
            pr.match_id,
            pr.run_type,
            pr.model_version,
            pr.as_of_time,
            pr.home_win_prob,
            pr.draw_prob,
            pr.away_win_prob,
            m.match_date,
            m.competition,
            COALESCE(m.stage, '') AS stage,
            COALESCE(m.is_neutral_venue, 0) AS is_neutral_venue,
            mr.home_goals,
            mr.away_goals
        FROM prediction_runs pr
        JOIN matches m
          ON REPLACE(CAST(pr.match_id AS TEXT), '-', '') = REPLACE(CAST(m.id AS TEXT), '-', '')
        JOIN match_results mr
          ON REPLACE(CAST(mr.match_id AS TEXT), '-', '') = REPLACE(CAST(m.id AS TEXT), '-', '')
        WHERE mr.home_goals IS NOT NULL
          AND mr.away_goals IS NOT NULL
        ORDER BY pr.as_of_time ASC
    """
    if limit:
        query += " LIMIT ?"
        return list(conn.execute(query, (limit,)))
    return list(conn.execute(query))


def _load_snapshot_rows(conn: sqlite3.Connection, limit: int | None) -> list[sqlite3.Row]:
    query = """
        SELECT
            'prediction_snapshots' AS source,
            ps.id,
            ps.match_id,
            ps.run_type,
            ps.model_version,
            ps.generated_at AS as_of_time,
            ps.baseline_probs,
            ps.adjusted_probs,
            ps.component_probs,
            ps.market_probs,
            m.match_date,
            m.competition,
            COALESCE(m.stage, '') AS stage,
            COALESCE(m.is_neutral_venue, 0) AS is_neutral_venue,
            mr.home_goals,
            mr.away_goals
        FROM prediction_snapshots ps
        JOIN matches m
          ON REPLACE(CAST(ps.match_id AS TEXT), '-', '') = REPLACE(CAST(m.id AS TEXT), '-', '')
        JOIN match_results mr
          ON REPLACE(CAST(mr.match_id AS TEXT), '-', '') = REPLACE(CAST(m.id AS TEXT), '-', '')
        WHERE mr.home_goals IS NOT NULL
          AND mr.away_goals IS NOT NULL
          AND ps.match_id IS NOT NULL
          AND TRIM(ps.match_id) <> ''
        ORDER BY ps.generated_at ASC
    """
    if limit:
        query += " LIMIT ?"
        return list(conn.execute(query, (limit,)))
    return list(conn.execute(query))


def _json_obj(raw: object) -> dict:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(str(raw))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _prob_tuple(data: dict) -> tuple[float, float, float] | None:
    home = data.get("home", data.get("home_win_prob"))
    draw = data.get("draw", data.get("draw_prob"))
    away = data.get("away", data.get("away_win_prob"))
    if home is None or draw is None or away is None:
        return None
    return (float(home), float(draw), float(away))


def _component_label(name: str) -> str:
    normalized = name.lower()
    return {
        "dc": "dc_only",
        "dixon_coles": "dc_only",
        "enhancer": "tabular_only",
        "tabular": "tabular_only",
        "elo": "elo_only",
        "pi": "pi_only",
        "pi_rating": "pi_only",
        "weibull": "weibull_only",
        "market": "market_only",
    }.get(normalized, f"component:{normalized}")


def _split_group_label(label: str) -> tuple[str, str]:
    if "::" not in label:
        return label, ""
    return label.rsplit("::", 1)


def _summary_map(aggregates: dict[str, Aggregate], min_sample: int = 0) -> dict[str, dict[str, float | int]]:
    return {
        label: agg.averages()
        for label, agg in sorted(aggregates.items())
        if agg.n >= min_sample
    }


def _better_metric_count(candidate: dict[str, Any], baseline: dict[str, Any]) -> int:
    return sum(float(candidate[metric]) < float(baseline[metric]) for metric in PROPER_METRICS)


def _metric_delta(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, float]:
    return {metric: float(candidate[metric]) - float(baseline[metric]) for metric in PROPER_METRICS}


def _find_group_regressions(
    groups: dict[str, Aggregate],
    *,
    group_name: str,
    champion_label: str,
    baseline_label: str,
    group_min_sample: int,
    max_group_regression: float,
) -> list[dict[str, Any]]:
    by_group: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for label, agg in groups.items():
        group_value, metric_label = _split_group_label(label)
        if agg.n >= group_min_sample:
            by_group[group_value][metric_label] = agg.averages()

    regressions: list[dict[str, Any]] = []
    for group_value, labels in sorted(by_group.items()):
        champion = labels.get(champion_label)
        baseline = labels.get(baseline_label)
        if not champion or not baseline:
            continue
        deltas = _metric_delta(champion, baseline)
        bad_metrics = {
            metric: delta
            for metric, delta in deltas.items()
            if metric in {"log_loss", "brier"} and delta > max_group_regression
        }
        if bad_metrics:
            regressions.append(
                {
                    "group_type": group_name,
                    "group": group_value,
                    "champion": champion,
                    "baseline": baseline,
                    "deltas": deltas,
                    "bad_metrics": bad_metrics,
                }
            )
    return regressions


def decide_champion_gate(
    *,
    leaderboard: dict[str, Aggregate],
    by_horizon: dict[str, Aggregate],
    by_competition: dict[str, Aggregate],
    by_run_type: dict[str, Aggregate],
    config: GateConfig,
) -> dict[str, Any]:
    eligible = _summary_map(leaderboard, config.min_sample)
    reasons: list[str] = []
    warnings: list[str] = []
    comparisons: dict[str, Any] = {}

    champion = eligible.get(config.champion_label)
    if champion is None:
        reasons.append(f"champion '{config.champion_label}' has fewer than {config.min_sample} samples")

    leader_label = None
    if eligible:
        leader_label = min(
            eligible,
            key=lambda label: (
                float(eligible[label]["log_loss"]),
                float(eligible[label]["brier"]),
                float(eligible[label]["rps"]),
                label,
            ),
        )
        if champion is not None and leader_label != config.champion_label:
            reasons.append(f"champion is not leaderboard leader by log_loss: leader={leader_label}")

    if champion is not None:
        uniform = eligible.get("uniform_baseline")
        if uniform is None:
            reasons.append("uniform_baseline has insufficient samples for required gate comparison")
        else:
            comparisons["uniform_baseline"] = {
                "baseline": uniform,
                "deltas": _metric_delta(champion, uniform),
                "better_metric_count": _better_metric_count(champion, uniform),
            }
            if float(champion["log_loss"]) >= float(uniform["log_loss"]):
                reasons.append("champion log_loss is not better than uniform_baseline")
            if float(champion["brier"]) >= float(uniform["brier"]):
                reasons.append("champion brier is not better than uniform_baseline")
            if _better_metric_count(champion, uniform) < 2:
                reasons.append("champion does not beat uniform_baseline on at least two proper scoring metrics")

        for baseline_label in ["dc_only", "elo_only", "pi_only", "weibull_only", "tabular_only", "market_only"]:
            baseline = eligible.get(baseline_label)
            if baseline is None:
                warnings.append(f"{baseline_label} has fewer than {config.min_sample} samples")
                continue
            comparisons[baseline_label] = {
                "baseline": baseline,
                "deltas": _metric_delta(champion, baseline),
                "better_metric_count": _better_metric_count(champion, baseline),
                "paired": False,
                "note": "unpaired benchmark; sample sets may differ",
            }

    group_regressions: list[dict[str, Any]] = []
    for group_name, groups in [
        ("horizon", by_horizon),
        ("competition", by_competition),
        ("run_type", by_run_type),
    ]:
        group_regressions.extend(
            _find_group_regressions(
                groups,
                group_name=group_name,
                champion_label=config.champion_label,
                baseline_label="uniform_baseline",
                group_min_sample=config.group_min_sample,
                max_group_regression=config.max_group_regression,
            )
        )
    if group_regressions:
        reasons.append(f"champion has {len(group_regressions)} critical group regression(s) vs uniform_baseline")

    return {
        "status": "pass" if not reasons else "fail",
        "champion_label": config.champion_label,
        "leader_label": leader_label,
        "min_sample": config.min_sample,
        "group_min_sample": config.group_min_sample,
        "max_group_regression": config.max_group_regression,
        "champion": champion,
        "eligible_labels": sorted(eligible),
        "comparisons": comparisons,
        "group_regressions": group_regressions,
        "reasons": reasons,
        "warnings": warnings,
    }


def _record_context(
    *,
    row: sqlite3.Row,
    metrics_label: str,
    metrics: ThreeWayMetrics,
    horizon: str,
    by_model: dict[str, Aggregate],
    by_run_type: dict[str, Aggregate],
    by_competition: dict[str, Aggregate],
    by_horizon: dict[str, Aggregate],
) -> None:
    agg = Aggregate()
    agg.add_metrics(metrics)
    by_model[f"{row['model_version']}::{metrics_label}"].merge(agg)
    by_run_type[f"{row['run_type']}::{metrics_label}"].merge(agg)
    by_competition[f"{row['competition']}::{metrics_label}"].merge(agg)
    by_horizon[f"{horizon}::{metrics_label}"].merge(agg)


def _add_prediction_metrics(
    aggregates: dict[str, Aggregate],
    *,
    label: str,
    home_prob: float,
    draw_prob: float,
    away_prob: float,
    home_goals: int,
    away_goals: int,
) -> ThreeWayMetrics:
    metrics = evaluate_three_way(
        home_prob=home_prob,
        draw_prob=draw_prob,
        away_prob=away_prob,
        home_goals=home_goals,
        away_goals=away_goals,
    )
    aggregates[label].add_metrics(metrics)
    return metrics


def build_walk_forward_report(
    *,
    conn: sqlite3.Connection,
    db_path: str,
    limit: int | None,
    min_sample: int,
    group_min_sample: int,
    max_group_regression: float,
    champion_label: str,
) -> dict[str, Any]:
    run_rows = _load_prediction_run_rows(conn, limit)
    snapshot_rows = _load_snapshot_rows(conn, limit)

    by_baseline: dict[str, Aggregate] = defaultdict(Aggregate)
    by_model: dict[str, Aggregate] = defaultdict(Aggregate)
    by_run_type: dict[str, Aggregate] = defaultdict(Aggregate)
    by_competition: dict[str, Aggregate] = defaultdict(Aggregate)
    by_horizon: dict[str, Aggregate] = defaultdict(Aggregate)
    skipped_after_kickoff = 0
    skipped_bad_time = 0

    for row in run_rows:
        as_of_time = _parse_time(row["as_of_time"])
        kickoff = _parse_time(row["match_date"])
        if as_of_time is None or kickoff is None:
            skipped_bad_time += 1
            continue
        if as_of_time > kickoff:
            skipped_after_kickoff += 1
            continue
        horizon = _horizon(as_of_time, kickoff)

        current_metrics = _add_prediction_metrics(
            by_baseline,
            label="current_fusion",
            home_prob=row["home_win_prob"],
            draw_prob=row["draw_prob"],
            away_prob=row["away_win_prob"],
            home_goals=row["home_goals"],
            away_goals=row["away_goals"],
        )
        _record_context(
            row=row,
            metrics_label="current_fusion",
            metrics=current_metrics,
            horizon=horizon,
            by_model=by_model,
            by_run_type=by_run_type,
            by_competition=by_competition,
            by_horizon=by_horizon,
        )

        uniform_metrics = _add_prediction_metrics(
            by_baseline,
            label="uniform_baseline",
            home_prob=1 / 3,
            draw_prob=1 / 3,
            away_prob=1 / 3,
            home_goals=row["home_goals"],
            away_goals=row["away_goals"],
        )
        _record_context(
            row=row,
            metrics_label="uniform_baseline",
            metrics=uniform_metrics,
            horizon=horizon,
            by_model=by_model,
            by_run_type=by_run_type,
            by_competition=by_competition,
            by_horizon=by_horizon,
        )

    for row in snapshot_rows:
        as_of_time = _parse_time(row["as_of_time"])
        kickoff = _parse_time(row["match_date"])
        if as_of_time is None or kickoff is None:
            skipped_bad_time += 1
            continue
        if as_of_time > kickoff:
            skipped_after_kickoff += 1
            continue
        horizon = _horizon(as_of_time, kickoff)

        candidates: list[tuple[str, tuple[float, float, float]]] = []
        for label, raw in [
            ("snapshot_baseline", row["baseline_probs"]),
            ("snapshot_adjusted", row["adjusted_probs"]),
            ("market_only", row["market_probs"]),
        ]:
            probs = _prob_tuple(_json_obj(raw))
            if probs:
                candidates.append((label, probs))

        for name, probs_obj in _json_obj(row["component_probs"]).items():
            if isinstance(probs_obj, dict):
                probs = _prob_tuple(probs_obj)
                if probs:
                    candidates.append((_component_label(name), probs))

        for label, probs in candidates:
            metrics = _add_prediction_metrics(
                by_baseline,
                label=label,
                home_prob=probs[0],
                draw_prob=probs[1],
                away_prob=probs[2],
                home_goals=row["home_goals"],
                away_goals=row["away_goals"],
            )
            _record_context(
                row=row,
                metrics_label=label,
                metrics=metrics,
                horizon=horizon,
                by_model=by_model,
                by_run_type=by_run_type,
                by_competition=by_competition,
                by_horizon=by_horizon,
            )

    gate = decide_champion_gate(
        leaderboard=by_baseline,
        by_horizon=by_horizon,
        by_competition=by_competition,
        by_run_type=by_run_type,
        config=GateConfig(
            champion_label=champion_label,
            min_sample=min_sample,
            group_min_sample=group_min_sample,
            max_group_regression=max_group_regression,
        ),
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_path": db_path,
        "min_sample": min_sample,
        "group_min_sample": group_min_sample,
        "max_group_regression": max_group_regression,
        "loaded": {
            "prediction_runs": len(run_rows),
            "prediction_snapshots": len(snapshot_rows),
            "current_fusion_evaluated": by_baseline["current_fusion"].n,
            "skipped_after_kickoff": skipped_after_kickoff,
            "skipped_bad_timestamps": skipped_bad_time,
        },
        "leaderboard": _summary_map(by_baseline),
        "groups": {
            "model_version": _summary_map(by_model),
            "run_type": _summary_map(by_run_type),
            "competition": _summary_map(by_competition),
            "horizon": _summary_map(by_horizon),
        },
        "gate": gate,
    }


def _sorted_items(summary: dict[str, dict[str, Any]], min_sample: int) -> list[tuple[str, dict[str, Any]]]:
    return sorted(
        ((label, row) for label, row in summary.items() if int(row["n"]) >= min_sample),
        key=lambda item: (float(item[1]["log_loss"]), float(item[1]["brier"]), item[0]),
    )


def _print_summary(report: dict[str, Any], *, min_sample: int) -> None:
    print("=" * 78)
    print("WALK-FORWARD CHAMPION GATE: stored prediction_runs + prediction_snapshots")
    print("=" * 78)
    print(f"DB: {report['db_path']}")
    print(f"PredictionRun rows loaded: {report['loaded']['prediction_runs']}")
    print(f"PredictionSnapshot rows loaded: {report['loaded']['prediction_snapshots']}")
    print(f"Current fusion rows evaluated: {report['loaded']['current_fusion_evaluated']}")
    print(f"Skipped after kickoff: {report['loaded']['skipped_after_kickoff']}")
    print(f"Skipped bad timestamps: {report['loaded']['skipped_bad_timestamps']}")

    print("\n--- model / baseline leaderboard ---")
    for label, row in _sorted_items(report["leaderboard"], min_sample):
        print(
            f"{label:42} n={int(row['n']):4d} "
            f"log_loss={float(row['log_loss']):.4f} "
            f"brier={float(row['brier']):.4f} "
            f"rps={float(row['rps']):.4f} "
            f"acc={float(row['accuracy']):.3f}"
        )

    for group_name, title in [
        ("model_version", "by model_version"),
        ("run_type", "by run_type"),
        ("competition", "by competition"),
        ("horizon", "by horizon"),
    ]:
        print(f"\n--- {title} ---")
        items = sorted(
            ((label, row) for label, row in report["groups"][group_name].items() if int(row["n"]) >= min_sample),
            key=lambda item: (-int(item[1]["n"]), item[0]),
        )
        for label, row in items:
            print(
                f"{label[:42]:42} n={int(row['n']):4d} "
                f"log_loss={float(row['log_loss']):.4f} "
                f"brier={float(row['brier']):.4f} "
                f"rps={float(row['rps']):.4f} "
                f"acc={float(row['accuracy']):.3f}"
            )

    gate = report["gate"]
    print("\n--- champion gate ---")
    print(f"status: {gate['status'].upper()}")
    print(f"champion: {gate['champion_label']}")
    print(f"leader: {gate['leader_label']}")
    if gate["reasons"]:
        print("reasons:")
        for reason in gate["reasons"]:
            print(f"  - {reason}")
    if gate["warnings"]:
        print("warnings:")
        for warning in gate["warnings"]:
            print(f"  - {warning}")


def _markdown_table(rows: list[tuple[str, dict[str, Any]]]) -> str:
    lines = ["| Label | n | log loss | Brier | RPS | Accuracy |", "|---|---:|---:|---:|---:|---:|"]
    for label, row in rows:
        lines.append(
            f"| {label} | {int(row['n'])} | {float(row['log_loss']):.4f} | "
            f"{float(row['brier']):.4f} | {float(row['rps']):.4f} | {float(row['accuracy']):.3f} |"
        )
    return "\n".join(lines)


def _render_markdown(report: dict[str, Any], *, min_sample: int) -> str:
    gate = report["gate"]
    lines = [
        "# Walk-forward Champion Gate Report",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- DB: `{report['db_path']}`",
        f"- Gate status: **{gate['status'].upper()}**",
        f"- Champion: `{gate['champion_label']}`",
        f"- Leader: `{gate['leader_label']}`",
        f"- Current fusion rows: `{report['loaded']['current_fusion_evaluated']}`",
        "",
        "## Gate Reasons",
    ]
    if gate["reasons"]:
        lines.extend(f"- {reason}" for reason in gate["reasons"])
    else:
        lines.append("- None")
    if gate["warnings"]:
        lines.extend(["", "## Warnings"])
        lines.extend(f"- {warning}" for warning in gate["warnings"])
    lines.extend(["", "## Leaderboard", _markdown_table(_sorted_items(report["leaderboard"], min_sample))])
    if gate["group_regressions"]:
        lines.extend(["", "## Group Regressions"])
        for item in gate["group_regressions"]:
            lines.append(
                f"- `{item['group_type']}` `{item['group']}`: bad_metrics={item['bad_metrics']}"
            )
    return "\n".join(lines) + "\n"


def _write_reports(
    report: dict[str, Any],
    *,
    report_dir: Path,
    json_out: str | None,
    markdown_out: str | None,
    min_sample: int,
) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = Path(json_out) if json_out else report_dir / f"walk_forward_champion_gate_{stamp}.json"
    markdown_path = Path(markdown_out) if markdown_out else report_dir / f"walk_forward_champion_gate_{stamp}.md"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_render_markdown(report, min_sample=min_sample), encoding="utf-8")
    return json_path, markdown_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate stored predictions with walk-forward champion gates.")
    parser.add_argument("--db", default=str(PROJECT_ROOT / "data" / "local_stage2.db"))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--min-sample", type=int, default=20)
    parser.add_argument("--group-min-sample", type=int, default=5)
    parser.add_argument("--max-group-regression", type=float, default=0.02)
    parser.add_argument("--champion-label", default="current_fusion")
    parser.add_argument("--enforce-gate", action="store_true", help="Exit non-zero when the champion gate fails.")
    parser.add_argument("--report-dir", default=str(PROJECT_ROOT / "reports"))
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--markdown-out", default=None)
    args = parser.parse_args(argv)

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    try:
        report = build_walk_forward_report(
            conn=conn,
            db_path=args.db,
            limit=args.limit,
            min_sample=args.min_sample,
            group_min_sample=args.group_min_sample,
            max_group_regression=args.max_group_regression,
            champion_label=args.champion_label,
        )
    finally:
        conn.close()

    _print_summary(report, min_sample=args.min_sample)
    json_path, markdown_path = _write_reports(
        report,
        report_dir=Path(args.report_dir),
        json_out=args.json_out,
        markdown_out=args.markdown_out,
        min_sample=args.min_sample,
    )
    print(f"\nJSON report: {json_path}")
    print(f"Markdown report: {markdown_path}")

    if report["loaded"]["current_fusion_evaluated"] < args.min_sample:
        print(
            f"\nFAIL: only {report['loaded']['current_fusion_evaluated']} current_fusion rows; "
            f"need at least {args.min_sample}."
        )
        return 2
    if args.enforce_gate and report["gate"]["status"] != "pass":
        print("\nFAIL: champion gate rejected current champion.")
        return 2
    print("\nOK: walk-forward report generated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
