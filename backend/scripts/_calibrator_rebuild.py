"""Rebuild probability calibrator from actual match results.

Fixes the broken calibrator.json (all y_thresholds = [0.0, 0.0]) by:
1. Extracting all prediction-vs-actual pairs from DB
2. Fitting IsotonicRegression on real data
3. Saving the corrected calibrator.json
4. Computing Expected Calibration Error (ECE) and reliability diagram data
"""
from __future__ import annotations

import json
import math
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

# Fix Windows GBK encoding for emoji characters
import io
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB_PATH = BACKEND_DIR / "data" / "local_stage2.db"
CALIBRATOR_PATH = BACKEND_DIR / "artifacts" / "calibrator.json"


def extract_prediction_actual_pairs(db_path: Path, competition_filter: str = None) -> list[dict]:
    """Extract all prediction-actual pairs with both prediction probs and actual results.

    Returns list of dicts with:
        home_team, away_team, competition, model_version,
        pred_h, pred_d, pred_a (predicted probabilities 0-1),
        actual_result ('H', 'D', 'A'),
        actual_home_goals, actual_away_goals,
        pred_hxg, pred_axg, actual_hxg, actual_axg
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Get unique prediction snapshots with actual results
    query = """
        SELECT DISTINCT
            ps.id, ps.home_team, ps.away_team, ps.competition, ps.model_version,
            ps.baseline_probs, ps.adjusted_probs, ps.component_probs, ps.expected_goals, ps.elo_ratings,
            mr.home_goals, mr.away_goals, mr.home_xg, mr.away_xg
        FROM prediction_snapshots ps
        JOIN match_results mr ON ps.match_id = mr.match_id
        WHERE mr.home_goals IS NOT NULL
          AND ps.baseline_probs IS NOT NULL
    """
    if competition_filter:
        query += f" AND ps.competition LIKE '%{competition_filter}%'"
    query += " ORDER BY ps.generated_at DESC"

    c.execute(query)

    pairs = []
    seen_keys = set()

    for row in c.fetchall():
        # Deduplicate by (home_team, away_team, home_goals, away_goals) — same match
        # Keep the snapshot with REAL baseline_probs (not default 0.33/0.33/0.33)
        key = (row["home_team"], row["away_team"], row["home_goals"], row["away_goals"])
        if key in seen_keys:
            continue

        try:
            baseline = json.loads(row["baseline_probs"]) if row["baseline_probs"] else {}
        except (json.JSONDecodeError, TypeError):
            baseline = {}

        # Try adjusted_probs as fallback (some snapshots store predictions there)
        if not baseline or not isinstance(baseline, dict) or all(
            not isinstance(baseline.get(k), (int, float)) for k in ["home", "draw", "away", "home_win_prob", "draw_prob", "away_win_prob"]
        ):
            try:
                adjusted = json.loads(row["adjusted_probs"]) if row["adjusted_probs"] else {}
                if isinstance(adjusted, dict) and any(
                    isinstance(adjusted.get(k), (int, float)) for k in ["home", "draw", "away", "home_win_prob", "draw_prob", "away_win_prob"]
                ):
                    baseline = adjusted
            except (json.JSONDecodeError, TypeError):
                pass

        try:
            xg = json.loads(row["expected_goals"]) if row["expected_goals"] else {}
        except (json.JSONDecodeError, TypeError):
            xg = {}

        pred_h = baseline.get("home", baseline.get("home_win_prob", None))
        pred_d = baseline.get("draw", baseline.get("draw_prob", None))
        pred_a = baseline.get("away", baseline.get("away_win_prob", None))

        # Skip if probs are None or string or otherwise invalid
        if any(not isinstance(v, (int, float)) for v in [pred_h, pred_d, pred_a]):
            continue
        if pred_h + pred_d + pred_a < 0.01:
            continue
        if abs(pred_h + pred_d + pred_a - 1.0) > 0.2:
            # Skip garbage — probabilities should sum to ~1.0
            continue
        # Also skip obvious default 0.33/0.33/0.33 (the pipeline fills defaults this way)
        if abs(pred_h - 0.33) < 0.001 and abs(pred_d - 0.33) < 0.001 and abs(pred_a - 0.33) < 0.001:
            continue

        seen_keys.add(key)

        hg = row["home_goals"]
        ag = row["away_goals"]
        if hg > ag:
            actual = "H"
        elif hg == ag:
            actual = "D"
        else:
            actual = "A"

        pairs.append({
            "home_team": row["home_team"],
            "away_team": row["away_team"],
            "competition": row["competition"],
            "model_version": row["model_version"],
            "pred_h": pred_h,
            "pred_d": pred_d,
            "pred_a": pred_a,
            "actual_result": actual,
            "actual_home_goals": hg,
            "actual_away_goals": ag,
            "pred_hxg": xg.get("home"),
            "pred_axg": xg.get("away"),
            "actual_hxg": row["home_xg"],
            "actual_axg": row["away_xg"],
        })

    conn.close()
    return pairs


def fit_calibrator(pairs: list[dict]) -> dict:
    """Fit isotonic calibration curves and return calibrator artifact."""
    from sklearn.isotonic import IsotonicRegression

    calibrators = {}
    ece_values = []

    for key, prob_field in [("home_win", "pred_h"), ("draw", "pred_d"), ("away_win", "pred_a")]:
        x = np.asarray([p[prob_field] for p in pairs], dtype=float)
        y = np.asarray([
            1.0 if p["actual_result"] == {"home_win": "H", "draw": "D", "away_win": "A"}[key]
            else 0.0
            for p in pairs
        ], dtype=float)

        if len(np.unique(y)) < 2:
            # All same outcome — can't fit
            print(f"  WARNING: {key} has no variation in outcomes, skipping")
            calibrators[key] = None
            continue

        try:
            cal = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
            cal.fit(x, y)
            calibrators[key] = {
                "x_thresholds": [float(t) for t in cal.X_thresholds_.tolist()],
                "y_thresholds": [float(t) for t in cal.y_thresholds_.tolist()],
            }
            # Compute ECE
            y_pred = cal.predict(x)
            ece = compute_ece(x, y_pred, y)
            ece_values.append(ece)
            print(f"  {key}: thresholds={len(cal.X_thresholds_)} ECE={ece:.4f}")
        except Exception as e:
            print(f"  ERROR fitting {key}: {e}")
            calibrators[key] = None

    return {
        "is_fitted": any(c is not None for c in calibrators.values()),
        "fitted_at": datetime.now(timezone.utc).isoformat(),
        "training_sample_count": len(pairs),
        "expected_calibration_error": float(np.mean(ece_values)) if ece_values else 0.0,
        "calibrators": calibrators,
    }


def compute_ece(raw_probs: np.ndarray, calibrated_probs: np.ndarray, labels: np.ndarray, bins: int = 10) -> float:
    """Expected Calibration Error using equal-width binning."""
    if len(raw_probs) == 0:
        return 0.0
    bucket_edges = np.linspace(0.0, 1.0, bins + 1)
    ece = 0.0
    total = len(raw_probs)
    for idx in range(bins):
        lower = bucket_edges[idx]
        upper = bucket_edges[idx + 1]
        if idx == bins - 1:
            mask = (raw_probs >= lower) & (raw_probs <= upper)
        else:
            mask = (raw_probs >= lower) & (raw_probs < upper)
        if not np.any(mask):
            continue
        avg_conf = float(np.mean(calibrated_probs[mask]))
        avg_acc = float(np.mean(labels[mask]))
        ece += abs(avg_conf - avg_acc) * (int(np.sum(mask)) / total)
    return float(ece)


def compute_brier(pairs: list[dict]) -> dict:
    """Compute Brier scores for each class and overall."""
    total = len(pairs)
    brier_total = 0.0
    brier_per_class = {"H": 0.0, "D": 0.0, "A": 0.0}
    counts = {"H": 0, "D": 0, "A": 0}

    for p in pairs:
        actual_idx = {"H": 0, "D": 1, "A": 2}[p["actual_result"]]
        actual_vec = [0.0, 0.0, 0.0]
        actual_vec[actual_idx] = 1.0
        pred_vec = [p["pred_h"], p["pred_d"], p["pred_a"]]
        brier = sum((pv - av) ** 2 for pv, av in zip(pred_vec, actual_vec))
        brier_total += brier
        brier_per_class[p["actual_result"]] += brier
        counts[p["actual_result"]] += 1

    result = {"overall": brier_total / total if total > 0 else float('inf'), "total_pairs": total}
    for cls in ["H", "D", "A"]:
        result[f"class_{cls}"] = brier_per_class[cls] / counts[cls] if counts[cls] > 0 else float('inf')
        result[f"count_{cls}"] = counts[cls]

    return result


def compute_baseline_brier(pairs: list[dict], baseline_name: str) -> dict:
    """Compute Brier score for a simple baseline strategy."""
    total = len(pairs)
    brier_total = 0.0

    for p in pairs:
        actual_idx = {"H": 0, "D": 1, "A": 2}[p["actual_result"]]
        actual_vec = [0.0, 0.0, 0.0]
        actual_vec[actual_idx] = 1.0

        if baseline_name == "uniform":
            pred_vec = [1 / 3, 1 / 3, 1 / 3]
        elif baseline_name == "always_home":
            pred_vec = [1.0, 0.0, 0.0]
        elif baseline_name == "always_draw":
            pred_vec = [0.0, 1.0, 0.0]
        elif baseline_name == "always_away":
            pred_vec = [0.0, 0.0, 1.0]
        elif baseline_name == "home_draw_away_50_30_20":
            # Common market prior
            pred_vec = [0.50, 0.30, 0.20]
        elif baseline_name == "avg_historical":
            # Average of actual outcomes in the data
            h_count = sum(1 for p2 in pairs if p2["actual_result"] == "H")
            d_count = sum(1 for p2 in pairs if p2["actual_result"] == "D")
            a_count = sum(1 for p2 in pairs if p2["actual_result"] == "A")
            pred_vec = [h_count / total, d_count / total, a_count / total]
        else:
            continue  # skip unknown baselines

        brier = sum((pv - av) ** 2 for pv, av in zip(pred_vec, actual_vec))
        brier_total += brier

    return {"baseline": baseline_name, "brier": brier_total / total if total > 0 else float('inf'), "total_pairs": total}


def save_calibrator(path: Path, artifact: dict) -> None:
    """Save calibrator artifact to disk, with parent directory creation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(artifact)
    if "fitted_at" in payload and isinstance(payload["fitted_at"], datetime):
        payload["fitted_at"] = payload["fitted_at"].isoformat()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def extract_component_data(db_path: Path, competition_filter: str = None) -> dict[str, float]:
    """Extract per-component Brier scores from prediction_learning_log.

    Returns dict mapping component_name -> average marginal contribution.
    Lower = better component.
    """
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()

    query = """
        SELECT pll.dc_marginal, pll.enhancer_marginal, pll.elo_marginal
        FROM prediction_learning_log pll
        JOIN prediction_snapshots ps ON pll.snapshot_id = ps.id
    """
    if competition_filter:
        query += f" WHERE ps.competition LIKE '%{competition_filter}%'"
    query += " ORDER BY pll.created_at DESC"

    c.execute(query)
    rows = c.fetchall()
    conn.close()

    if not rows:
        return {}

    # Marginal contribution to Brier score (higher = worse).
    # Average across matches.
    dc_vals = [r[0] for r in rows if r[0] is not None]
    enh_vals = [r[1] for r in rows if r[1] is not None]
    elo_vals = [r[2] for r in rows if r[2] is not None]

    result = {}
    if dc_vals:
        result["DC"] = float(sum(dc_vals) / len(dc_vals))
    if enh_vals:
        result["Enhancer"] = float(sum(enh_vals) / len(enh_vals))
    if elo_vals:
        result["Elo"] = float(sum(elo_vals) / len(elo_vals))

    return result


def generate_report(pairs: list[dict], calibrator_artifact: dict, brier: dict, baselines: list[dict],
                    label: str = "全赛事混合", component_data: dict[str, float] = None) -> str:
    """Generate a human-readable calibration report."""
    lines = []
    lines.append(f"# 概率校准评估报告 — {label}")
    lines.append(f"")
    lines.append(f"**生成时间：** {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"**样本数量：** {len(pairs)} 场有实际赛果的预测")
    lines.append(f"")
    lines.append("---")
    lines.append("")
    lines.append("## 一、预测-实际对比总览")
    lines.append("")
    lines.append("| 主队 | 客队 | 赛事 | 预测(H/D/A) | 实际 | 预测xG | 实际xG |")
    lines.append("|------|------|------|------------|------|--------|--------|")

    for p in sorted(pairs, key=lambda x: (x["competition"] or "", x["home_team"] or "")):
        pred_str = f'{p["pred_h"]*100:.1f}%/{p["pred_d"]*100:.1f}%/{p["pred_a"]*100:.1f}%'
        actual_str = f'{p["actual_home_goals"]}-{p["actual_away_goals"]} ({p["actual_result"]})'
        pxg = f'{p["pred_hxg"]:.2f}/{p["pred_axg"]:.2f}' if p["pred_hxg"] is not None else "N/A"
        axg = f'{p["actual_hxg"]:.2f}/{p["actual_axg"]:.2f}' if p["actual_hxg"] is not None else "N/A"
        lines.append(f'| {p["home_team"]} | {p["away_team"]} | {p["competition"]} | {pred_str} | {actual_str} | {pxg} | {axg} |')

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 二、Brier Score 对比")
    lines.append("")
    lines.append("| 模型/基准线 | Brier Score | 样本数 |")
    lines.append("|------------|:-----------:|:------:|")
    lines.append(f'| **V3.8.1 融合管道** | **{brier["overall"]:.4f}** | {brier["total_pairs"]} |')
    lines.append(f'|  · 主场胜 | {brier["class_H"]:.4f} | {brier["count_H"]} |')
    lines.append(f'|  · 平局 | {brier["class_D"]:.4f} | {brier["count_D"]} |')
    lines.append(f'|  · 客场胜 | {brier["class_A"]:.4f} | {brier["count_A"]} |')

    for bl in baselines:
        lines.append(f'| {bl["baseline"]} | {bl["brier"]:.4f} | {bl["total_pairs"]} |')

    if component_data:
        lines.append("")
        lines.append("### 分组件 Brier 边际贡献")
        lines.append("")
        lines.append("| 组件 | 平均边际贡献 | 解读 |")
        lines.append("|------|:-----------:|------|")
        for comp_name, comp_val in sorted(component_data.items()):
            # In Brier space, LOWER = better. Positive marginal = ADDED error (bad).
            # Negative marginal = REDUCED error (good).
            direction = "🔴 增加误差" if comp_val > 0 else "🟢 减少误差"
            lines.append(f'| {comp_name} | {comp_val:+.4f} | {direction} |')

    # Determine if model beats baselines
    model_brier = brier["overall"]
    best_baseline = min(bl["brier"] for bl in baselines) if baselines else float('inf')
    if model_brier < best_baseline:
        lines.append(f"")
        lines.append(f"✅ **模型 Brier ({model_brier:.4f}) 优于所有基准线（最佳: {best_baseline:.4f}），差值为 {best_baseline-model_brier:.4f}**")
    else:
        lines.append(f"")
        lines.append(f"❌ **模型 Brier ({model_brier:.4f}) 劣于最佳基准线 ({best_baseline:.4f})，差值为 {model_brier-best_baseline:.4f}**")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 三、概率校准曲线")
    lines.append("")
    lines.append(f'**保序回归状态：** {"已拟合" if calibrator_artifact["is_fitted"] else "未拟合"}')
    lines.append(f'**训练样本：** {calibrator_artifact["training_sample_count"]}')
    avg_ece = calibrator_artifact.get("expected_calibration_error", 0.0)
    lines.append(f'**期望校准误差 (ECE)：** {avg_ece:.4f}')
    lines.append("")

    for key, label in [("home_win", "主胜"), ("draw", "平局"), ("away_win", "客胜")]:
        cal = calibrator_artifact["calibrators"].get(key)
        if cal and cal["x_thresholds"]:
            lines.append(f"### {label}")
            lines.append(f"- 阈值点数: {len(cal['x_thresholds'])}")
            lines.append(f"- X 分位点: {[f'{x:.3f}' for x in cal['x_thresholds']]}")
            lines.append(f"- Y 校准值: {[f'{y:.3f}' for y in cal['y_thresholds']]}")
            # Check if it's degenerate (all 0 or all 1)
            y_vals = cal["y_thresholds"]
            if all(abs(y - y_vals[0]) < 1e-6 for y in y_vals):
                lines.append(f"- ⚠️ **退化曲线：** 所有校准值相同 ({y_vals[0]:.3f}) — 数据不足以拟合")
            lines.append("")
        else:
            lines.append(f"### {label}")
            lines.append(f"- ❌ 未能拟合")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 四、诊断结论")
    lines.append("")

    if len(pairs) < 20:
        lines.append(f"⚠️ **样本不足：** 仅有 {len(pairs)} 场比赛，保序回归需要至少 20 个样本才能可靠拟合。")
        lines.append(f"当前校准器无法提供有意义的校准。建议：收集更多比赛数据后重新拟合。")
    elif avg_ece > 0.1:
        lines.append(f"🔴 **校准较差：** ECE = {avg_ece:.4f}，模型概率与真实频率存在显著偏差。")
        lines.append(f"建议：在预测管道中启用校准器以修正系统性偏差。")
    elif avg_ece > 0.05:
        lines.append(f"🟡 **校准一般：** ECE = {avg_ece:.4f}，存在一定偏差。建议谨慎使用校准。")
    else:
        lines.append(f"🟢 **校准良好：** ECE = {avg_ece:.4f}，模型概率与真实频率基本一致。")

    if model_brier < best_baseline:
        lines.append(f"")
        lines.append(f"🟢 **模型 Brier ({model_brier:.4f}) 优于所有基准线。** 融合管道确实提供了超越简单规则的预测能力。")
    else:
        lines.append(f"")
        lines.append(f"🔴 **模型 Brier ({model_brier:.4f}) 不优于最佳基准线 ({best_baseline:.4f})。** 这可能因为：")
        lines.append(f"  - 样本量太小（{len(pairs)} 场）导致统计噪声淹没了模型优势")
        lines.append(f"  - 融合权重需要更多数据驱动调整")
        lines.append(f"  - 某些组件在特定场景下反而增加误差")

    lines.append("")
    lines.append(f"> 报告自动生成于 {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"> 校准器文件: `{CALIBRATOR_PATH}`")

    return "\n".join(lines)


def main():
    print("=" * 70)
    print("CALIBRATOR REBUILD — Step-by-step")
    print("=" * 70)

    # ===================================================================
    # PART A: Mixed-competition calibrator (for club + WC combined)
    # ===================================================================
    print("\n── PART A: Mixed-competition calibrator ──")
    all_pairs = extract_prediction_actual_pairs(DB_PATH)
    print(f"  Total pairs: {len(all_pairs)}")
    all_calibrator = fit_calibrator(all_pairs) if len(all_pairs) >= 20 else {"is_fitted": False, "calibrators": {}, "training_sample_count": 0, "expected_calibration_error": 0.0, "fitted_at": None}
    all_brier = compute_brier(all_pairs) if all_pairs else {"overall": 0, "total_pairs": 0}
    all_baselines = [compute_baseline_brier(all_pairs, bn) for bn in ["uniform", "always_home", "always_draw", "always_away", "home_draw_away_50_30_20", "avg_historical"]] if all_pairs else []

    save_calibrator(CALIBRATOR_PATH, all_calibrator)
    print(f"  Mixed calibrator saved: fitted={all_calibrator.get('is_fitted')}, samples={len(all_pairs)}")

    # ===================================================================
    # PART B: World Cup-only calibrator
    # ===================================================================
    print("\n── PART B: World Cup-only calibrator ──")
    wc_pairs = extract_prediction_actual_pairs(DB_PATH, competition_filter="World Cup")
    print(f"  World Cup pairs: {len(wc_pairs)}")

    wc_calibrator = None
    if len(wc_pairs) >= 20:
        wc_calibrator = fit_calibrator(wc_pairs)
        wc_cal_path = BACKEND_DIR / "artifacts" / "calibrator_wc.json"
        save_calibrator(wc_cal_path, wc_calibrator)
        print(f"  WC calibrator saved: fitted={wc_calibrator.get('is_fitted')}")
    else:
        print(f"  WARNING: Only {len(wc_pairs)} WC pairs — need ≥20 for reliable calibration")
        print(f"  WC calibrator NOT saved (advisory only)")
        wc_calibrator = {"is_fitted": False, "calibrators": {}, "training_sample_count": len(wc_pairs),
                         "expected_calibration_error": 0.0, "fitted_at": None,
                         "note": f"Insufficient samples ({len(wc_pairs)}/20 required)"}

    wc_brier = compute_brier(wc_pairs) if wc_pairs else {"overall": 0, "total_pairs": 0}
    wc_baselines = [compute_baseline_brier(wc_pairs, bn) for bn in ["uniform", "always_home", "always_draw", "always_away", "home_draw_away_50_30_20", "avg_historical"]] if wc_pairs else []

    # ===================================================================
    # PART C: WC-only component-level Brier analysis
    # ===================================================================
    print("\n── PART C: WC Component Brier Analysis ──")
    wc_component_data = extract_component_data(DB_PATH, competition_filter="World Cup")

    # ===================================================================
    # Generate consolidated report
    # ===================================================================
    print("\n── Generating Assessment Reports ──")

    # Mixed report
    mixed_report = generate_report(all_pairs, all_calibrator, all_brier, all_baselines,
                                   label="全赛事混合")
    report_path = BACKEND_DIR / "reports" / "CALIBRATION_ASSESSMENT.md"
    report_path.write_text(mixed_report, encoding="utf-8")
    print(f"  Mixed report: {report_path}")

    # WC-only report
    wc_report = generate_report(wc_pairs, wc_calibrator, wc_brier, wc_baselines,
                                label="World Cup 2026", component_data=wc_component_data)
    wc_report_path = BACKEND_DIR / "reports" / "CALIBRATION_ASSESSMENT_WC.md"
    wc_report_path.write_text(wc_report, encoding="utf-8")
    print(f"  WC report: {wc_report_path}")

    # Summary
    print("\n" + "=" * 70)
    print("CALIBRATOR REBUILD COMPLETE")
    print("=" * 70)

    # All-competition summary
    best_all = min(bl["brier"] for bl in all_baselines) if all_baselines else 0
    print(f"\n  Mixed (n={len(all_pairs)}):")
    print(f"    Model Brier:    {all_brier['overall']:.4f}")
    print(f"    Best Baseline:  {best_all:.4f}")
    print(f"    Delta:          {best_all - all_brier['overall']:.4f} " +
          ("(model ✓)" if all_brier['overall'] < best_all else "(baseline!)"))
    print(f"    ECE:            {all_calibrator.get('expected_calibration_error', 0):.4f}")

    # WC summary
    best_wc = min(bl["brier"] for bl in wc_baselines) if wc_baselines else 0
    print(f"\n  World Cup (n={len(wc_pairs)}):")
    print(f"    Model Brier:    {wc_brier['overall']:.4f}")
    print(f"    Best Baseline:  {best_wc:.4f}")
    delta_wc = best_wc - wc_brier['overall'] if wc_brier['overall'] > 0 else 0
    print(f"    Delta:          {delta_wc:.4f} " +
          ("(model ✓)" if wc_brier['overall'] < best_wc else "(baseline!)"))
    if wc_component_data:
        print(f"    Components:")
        for comp_name, comp_brier in sorted(wc_component_data.items()):
            print(f"      {comp_name:15s}: Brier={comp_brier:.4f}")

    print(f"\n  Calibrator status:")
    print(f"    Mixed:    {'fitted' if all_calibrator.get('is_fitted') else 'degenerate'} ({all_calibrator.get('training_sample_count', 0)} samples)")
    print(f"    WC-only:  {'fitted' if wc_calibrator and wc_calibrator.get('is_fitted') else 'insufficient data'} ({len(wc_pairs)} samples)")
    if len(wc_pairs) < 20:
        print(f"    ⚠ WC calibrator requires ≥20 samples to fit. Currently {len(wc_pairs)}. Will auto-fit when enough WC matches complete.")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
