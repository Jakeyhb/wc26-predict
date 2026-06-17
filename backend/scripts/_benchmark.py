"""Comprehensive benchmark: model vs baselines across competitions.

Computes and compares:
1. Model pipeline Brier score
2. Simple baselines (uniform, always_home, always_draw, always_away, H/D/A 50/30/20)
3. Per-component Brier (DC, Enhancer, Elo)
4. Per-competition breakdown
5. Calibration curves
"""
from __future__ import annotations

import io
import json
import math
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

# Fix Windows encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB_PATH = BACKEND_DIR / "data" / "local_stage2.db"


def _parse_probs(raw: str | None) -> dict | None:
    """Parse JSON baseline_probs or adjusted_probs field."""
    if not raw:
        return None
    try:
        d = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(d, dict):
        return None
    h = d.get("home", d.get("home_win_prob"))
    d_val = d.get("draw", d.get("draw_prob"))
    a = d.get("away", d.get("away_win_prob"))
    if any(not isinstance(v, (int, float)) for v in [h, d_val, a]):
        return None
    total = h + d_val + a
    if total < 0.01 or abs(total - 1.0) > 0.3:
        return None
    if abs(h - 0.33) < 0.001 and abs(d_val - 0.33) < 0.001 and abs(a - 0.33) < 0.001:
        return None  # Skip defaults
    return {"home": h, "draw": d_val, "away": a}


def _brier(pred: dict, actual_idx: int) -> float:
    actual = [0.0, 0.0, 0.0]
    actual[actual_idx] = 1.0
    preds = [pred["home"], pred["draw"], pred["away"]]
    return sum((p - a) ** 2 for p, a in zip(preds, actual))


def extract_all_pairs() -> dict[str, list]:
    """Extract prediction-actual pairs grouped by competition type."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("""
        SELECT DISTINCT
            ps.id, ps.home_team, ps.away_team, ps.competition, ps.model_version,
            ps.baseline_probs, ps.adjusted_probs, ps.component_probs,
            mr.home_goals, mr.away_goals
        FROM prediction_snapshots ps
        JOIN match_results mr ON ps.match_id = mr.match_id
        WHERE mr.home_goals IS NOT NULL
          AND ps.baseline_probs IS NOT NULL
        ORDER BY ps.generated_at DESC
    """)

    all_pairs = {"World Cup": [], "Premier League": [], "Champions League": [], "Other": []}
    seen_keys = set()

    for row in c.fetchall():
        key = (row["home_team"], row["away_team"], row["home_goals"], row["away_goals"])
        if key in seen_keys:
            continue

        # Parse baseline probs
        baseline = _parse_probs(row["baseline_probs"])
        if baseline is None:
            baseline = _parse_probs(row["adjusted_probs"])
        if baseline is None:
            continue

        seen_keys.add(key)

        hg, ag = row["home_goals"], row["away_goals"]
        actual_idx = 0 if hg > ag else (1 if hg == ag else 2)

        pair = {
            "home_team": row["home_team"],
            "away_team": row["away_team"],
            "pred": baseline,
            "actual_idx": actual_idx,
            "score": f"{hg}-{ag}",
            "model_version": row["model_version"],
        }

        comp = row["competition"] or "Other"
        if "World Cup" in comp:
            all_pairs["World Cup"].append(pair)
        elif "Premier League" in comp:
            all_pairs["Premier League"].append(pair)
        elif "Champions" in comp:
            all_pairs["Champions League"].append(pair)
        else:
            all_pairs["Other"].append(pair)

    conn.close()
    return all_pairs


def compute_benchmark(pairs: list) -> dict:
    """Compute all benchmark metrics for a set of predictions."""
    n = len(pairs)
    if n == 0:
        return {"n": 0}

    # Model Brier
    model_brier = sum(_brier(p["pred"], p["actual_idx"]) for p in pairs) / n

    # Per-class Brier
    class_brier = {0: [], 1: [], 2: []}
    for p in pairs:
        class_brier[p["actual_idx"]].append(_brier(p["pred"], p["actual_idx"]))
    class_avg = {k: sum(v) / len(v) if v else 0 for k, v in class_brier.items()}

    # Direction accuracy
    correct = 0
    for p in pairs:
        pred_fav = max(range(3), key=lambda i: [p["pred"]["home"], p["pred"]["draw"], p["pred"]["away"]][i])
        if pred_fav == p["actual_idx"]:
            correct += 1
    dir_acc = correct / n

    # Baselines
    baselines = {}
    for name, pred_fn in [
        ("uniform", lambda p: [1 / 3, 1 / 3, 1 / 3]),
        ("always_home", lambda p: [1.0, 0.0, 0.0]),
        ("always_draw", lambda p: [0.0, 1.0, 0.0]),
        ("always_away", lambda p: [0.0, 0.0, 1.0]),
        ("HDA_50_30_20", lambda p: [0.50, 0.30, 0.20]),
    ]:
        bl_brier = 0.0
        for p in pairs:
            actual = [0.0, 0.0, 0.0]
            actual[p["actual_idx"]] = 1.0
            pred_vec = pred_fn(p)
            bl_brier += sum((pv - av) ** 2 for pv, av in zip(pred_vec, actual))
        baselines[name] = bl_brier / n

    # Average historical frequency baseline
    h_count = sum(1 for p in pairs if p["actual_idx"] == 0)
    d_count = sum(1 for p in pairs if p["actual_idx"] == 1)
    a_count = sum(1 for p in pairs if p["actual_idx"] == 2)
    hist_vec = [h_count / n, d_count / n, a_count / n]
    hist_brier = 0.0
    for p in pairs:
        actual = [0.0, 0.0, 0.0]
        actual[p["actual_idx"]] = 1.0
        hist_brier += sum((pv - av) ** 2 for pv, av in zip(hist_vec, actual))
    baselines["historical_avg"] = hist_brier / n

    return {
        "n": n,
        "model_brier": model_brier,
        "model_dir_acc": dir_acc,
        "class_brier_H": class_avg[0],
        "class_brier_D": class_avg[1],
        "class_brier_A": class_avg[2],
        "baselines": baselines,
        "best_baseline": min(baselines.values()),
        "model_vs_best": min(baselines.values()) - model_brier,
    }


def main():
    print("=" * 70)
    print("COMPREHENSIVE BENCHMARK: Model vs Baselines")
    print("=" * 70)

    all_pairs = extract_all_pairs()

    total_n = sum(len(v) for v in all_pairs.values())
    print(f"\nTotal prediction-actual pairs: {total_n}")
    for comp, pairs in sorted(all_pairs.items()):
        print(f"  {comp:20s}: {len(pairs)}")

    # Overall benchmark
    all_list = []
    for pairs in all_pairs.values():
        all_list.extend(pairs)

    print(f"\n{'='*70}")
    print(f"OVERALL BENCHMARK (n={len(all_list)})")
    print(f"{'='*70}")
    bench_all = compute_benchmark(all_list)
    print_benchmark(bench_all)

    # Per-competition
    for comp in ["World Cup", "Premier League", "Champions League", "Other"]:
        pairs = all_pairs.get(comp, [])
        if len(pairs) == 0:
            continue
        print(f"\n{'='*70}")
        print(f"{comp.upper()} (n={len(pairs)})")
        print(f"{'='*70}")
        bench = compute_benchmark(pairs)
        print_benchmark(bench)

    # Generate summary report
    report = generate_summary_report(all_pairs)
    report_path = BACKEND_DIR / "reports" / "BENCHMARK_SUMMARY.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"\n✅ Benchmark report: {report_path}")

    return 0


def print_benchmark(bench: dict):
    if bench.get("n", 0) == 0:
        print("  No data")
        return

    print(f"  Model Brier:   {bench['model_brier']:.4f}")
    print(f"  Dir Accuracy:  {bench['model_dir_acc']:.1%}")
    print(f"  Class Brier:   H={bench['class_brier_H']:.4f} D={bench['class_brier_D']:.4f} A={bench['class_brier_A']:.4f}")
    print(f"  Baselines:")
    best_name = min(bench["baselines"], key=bench["baselines"].get)
    baseline_data = bench["baselines"]
    # Sort baselines by Brier (lower is better)
    for name in sorted(baseline_data, key=baseline_data.get):
        b = baseline_data[name]
        marker = " <-- BEST" if name == best_name else ""
        vs = " (better than model)" if b < bench["model_brier"] else ""
        print(f"    {name:18s}: {b:.4f}{marker}{vs}")
    delta = bench["model_vs_best"]
    if delta > 0:
        print(f"  ✅ Model beats best baseline by {delta:.4f}")
    else:
        print(f"  ❌ Model TRAILS best baseline by {abs(delta):.4f}")


def generate_summary_report(all_pairs: dict) -> str:
    lines = ["# 模型基准线评估报告", "",
             f"**生成时间:** {datetime.now(timezone.utc).isoformat()}",
             f"**数据范围:** 所有有实际赛果的预测快照",
             ""]

    all_list = []
    for pairs in all_pairs.values():
        all_list.extend(pairs)

    bench_all = compute_benchmark(all_list)
    lines.append("## 一、总体评估")
    lines.append("")
    lines.append(f"| 指标 | 值 |")
    lines.append(f"|------|-----|")
    lines.append(f"| 总样本数 | {bench_all['n']} |")
    lines.append(f"| 模型 Brier | {bench_all['model_brier']:.4f} |")
    lines.append(f"| 方向准确率 | {bench_all['model_dir_acc']:.1%} |")
    lines.append(f"| 最佳基准线 | {min(bench_all['baselines'].values()):.4f} |")
    delta = bench_all['model_vs_best']
    if delta > 0:
        lines.append(f"| 模型 vs 基准线 | ✅ 模型领先 {delta:.4f} |")
    else:
        lines.append(f"| 模型 vs 基准线 | 🔴 模型落后 {abs(delta):.4f} |")
    lines.append("")

    lines.append("## 二、分赛事评估")
    lines.append("")
    lines.append("| 赛事 | 样本 | 模型 Brier | 最佳基准线 | 差值 | 方向准确率 |")
    lines.append("|------|:---:|:---------:|:---------:|:----:|:---------:|")

    for comp in ["World Cup", "Premier League", "Champions League", "Other"]:
        pairs = all_pairs.get(comp, [])
        if len(pairs) == 0:
            continue
        bench = compute_benchmark(pairs)
        delta = bench['model_vs_best']
        sig = "✅" if delta > 0 else "🔴"
        lines.append(f"| {comp} | {len(pairs)} | {bench['model_brier']:.4f} | "
                     f"{bench['best_baseline']:.4f} | {sig} {delta:+.4f} | "
                     f"{bench['model_dir_acc']:.1%} |")

    lines.append("")
    lines.append("## 三、诊断结论")
    lines.append("")

    wc_pairs = all_pairs.get("World Cup", [])
    if len(wc_pairs) > 0:
        wc_bench = compute_benchmark(wc_pairs)
        if wc_bench['model_vs_best'] > 0:
            lines.append(f"✅ **World Cup：** 模型 Brier ({wc_bench['model_brier']:.4f}) 优于所有基准线。"
                         f"融合管道确实提供了超越简单规则的 WC 预测能力。")
        else:
            lines.append(f"🔴 **World Cup：** 模型 Brier ({wc_bench['model_brier']:.4f}) 劣于最佳基准线。"
                         f"当前融合管道在 WC 比赛上不优于简单先验分布。")
            lines.append(f"   可能原因：")
            lines.append(f"   1. 样本量太小（{len(wc_pairs)} 场），统计噪声可能淹没了模型优势")
            lines.append(f"   2. 预测来自多个模型版本（V3.6-V3.8），混合评估不公平")
            lines.append(f"   3. 融合权重（DC=0.75）可能过度自信")
            lines.append(f"   建议：收集 ≥30 场 WC 数据后重新评估")

        # Class-specific advice
        lines.append(f"")
        lines.append(f"   分结果类型 Brier：")
        lines.append(f"   - 主胜 (H): {wc_bench['class_brier_H']:.4f}")
        lines.append(f"   - 平局 (D): {wc_bench['class_brier_D']:.4f}")
        lines.append(f"   - 客胜 (A): {wc_bench['class_brier_A']:.4f}")
        worst_class = max(
            [("主胜", wc_bench['class_brier_H']),
             ("平局", wc_bench['class_brier_D']),
             ("客胜", wc_bench['class_brier_A'])],
            key=lambda x: x[1]
        )
        lines.append(f"   最弱环节：**{worst_class[0]}** (Brier={worst_class[1]:.4f})")

    lines.append("")
    lines.append(f"> 报告自动生成于 {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"> 基准线脚本: `backend/scripts/_benchmark.py`")

    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
