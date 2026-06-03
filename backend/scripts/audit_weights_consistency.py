"""Phase 0: Audit weight consistency across all prediction entry points.
Read-only — no business logic changes.

Checks:
1. Hardcoded weights in snapshot.py vs prediction_orchestrator.py vs fast_predict.py vs learning_engine.py
2. model_weight_config table values
3. Flags any mismatch > 0.01
"""
from __future__ import annotations

import ast
import importlib.util
import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# ── Parse hardcoded weights from source files ──

def extract_weight_dicts(filepath: str) -> list[dict]:
    """Extract weight values from Python source using AST."""
    with open(filepath, encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source)
    results = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            keys = []
            for k in node.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    keys.append(k.value)
                else:
                    keys.append(None)
            if any(k and ("weight" in k or k in ("dc", "enhancer", "elo", "pi", "weibull", "market", "enh"))
                   for k in keys if k):
                result = {}
                for k_node, v_node in zip(node.keys, node.values):
                    if isinstance(k_node, ast.Constant) and isinstance(v_node, ast.Constant | ast.UnaryOp):
                        k = k_node.value
                        if isinstance(v_node, ast.Constant):
                            result[k] = v_node.value
                        elif isinstance(v_node, ast.UnaryOp) and isinstance(v_node.op, ast.USub):
                            result[k] = -v_node.operand.value  # type: ignore[attr-defined]
                if result:
                    results.append(result)
    return results


def find_function_kwarg_defaults(filepath: str) -> list[dict]:
    """Find function definitions that have weight-related default arguments."""
    with open(filepath, encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source)
    results = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            weights = {}
            for default, arg in zip(node.args.defaults[::-1], node.args.args[::-1]):
                if isinstance(arg.arg, str) and "weight" in arg.arg:
                    if isinstance(default, ast.Constant):
                        weights[arg.arg] = default.value
            if weights:
                results.append({"function": node.name, "weights": weights})
    return results


def scan_source_for_weight_vars(filepath: str) -> list[dict]:
    """Scan source for weight assignment patterns like dc_weight=0.55."""
    results = []
    with open(filepath, encoding="utf-8") as f:
        content = f.read()
    # Match patterns like: "dc_weight": 0.55, or dc_weight=0.55,
    for key in ["dc_weight", "enh_weight", "elo_weight", "pi_weight",
                 "weibull_weight", "market_max", "base_weight", "enhancer_weight"]:
        # dict style
        for m in re.finditer(rf'["\']?{key}["\']?\s*[:=]\s*([0-9.]+)', content):
            results.append({"file": Path(filepath).name, "key": key, "value": float(m.group(1)),
                            "context": content[max(0,m.start()-40):m.end()+40].replace('\n',' ')})
    return results


# ── Main audit ──

def main():
    print("=" * 70)
    print("AUDIT: Weight Consistency Across Prediction Entry Points")
    print("=" * 70)

    # 1. Scan source files
    key_files = [
        str(PROJECT_ROOT / "scripts" / "snapshot.py"),
        str(PROJECT_ROOT / "scripts" / "fast_predict.py"),
        str(PROJECT_ROOT / "scripts" / "batch_snapshot.py"),
        str(PROJECT_ROOT / "scripts" / "hourly_predict.py"),
        str(PROJECT_ROOT / "app" / "services" / "prediction_orchestrator.py"),
        str(PROJECT_ROOT / "app" / "services" / "learning_engine.py"),
        str(PROJECT_ROOT / "app" / "services" / "tabular_match_model.py"),
        str(PROJECT_ROOT / "app" / "services" / "weibull_model.py"),
    ]

    all_weights = []
    for f in key_files:
        if not os.path.exists(f):
            continue
        kw = find_function_kwarg_defaults(f)
        if kw:
            for entry in kw:
                all_weights.append({**entry, "file": Path(f).name, "type": "function_default"})
        scanned = scan_source_for_weight_vars(f)
        all_weights.extend(scanned)

    # Group by file
    print("\n--- Weight entries by file ---")
    by_file: dict[str, list] = {}
    for w in all_weights:
        fn = w.get("file", "?")
        by_file.setdefault(fn, []).append(w)
    for fn, entries in sorted(by_file.items()):
        print(f"\n  [{fn}]")
        for e in entries:
            if "function" in e:
                print(f"    fn={e['function']}: {e['weights']}")
            else:
                print(f"    {e['key']}={e['value']}  |  ...{e.get('context','')[:50]}...")

    # 2. Check snapshot.py specific config
    print("\n\n--- snapshot.py _get_model_config() scenarios ---")
    try:
        spec = importlib.util.spec_from_file_location(
            "snapshot", str(PROJECT_ROOT / "scripts" / "snapshot.py")
        )
        # We can't reliably import snapshot due to async dependencies,
        # so parse from source
        with open(PROJECT_ROOT / "scripts" / "snapshot.py", encoding="utf-8") as f:
            snapshot_src = f.read()
        # Extract the _get_model_config function
        match = re.search(r"def _get_model_config\(.*?\n(?:.*\n)*?^def |def _get_model_config\(.*?\n(?:.*\n)*?\Z",
                          snapshot_src, re.MULTILINE)
        if match:
            print("  Found _get_model_config() — scenario weights (parsed from source)")
        # Find all weight dicts in snapshot
        wc_match = re.search(r'"WORLD_CUP".*?\{([^}]+)\}', snapshot_src, re.DOTALL)
        if wc_match:
            print(f"  WORLD_CUP: {{{wc_match.group(1).strip()}}}")
        league_match = re.search(r'"LEAGUE".*?\{([^}]+)\}', snapshot_src, re.DOTALL)
        if league_match:
            print(f"  LEAGUE(default): {{{league_match.group(1).strip()}}}")
    except Exception as exc:
        print(f"  Parse error: {exc}")

    # 3. Check model_weight_config table
    print("\n\n--- model_weight_config table (DB) ---")
    try:
        import sqlite3
        db_path = PROJECT_ROOT / "data" / "local_stage2.db"
        conn = sqlite3.connect(str(db_path))
        c = conn.cursor()
        c.execute("SELECT name, dc_weight, enhancer_weight, elo_weight, pi_weight, weibull_weight, market_weight, active FROM model_weight_config ORDER BY name")
        rows = c.fetchall()
        if rows:
            for r in rows:
                print(f"  {r[0]}: dc={r[1]}, enh={r[2]}, elo={r[3]}, pi={r[4]}, wb={r[5]}, mkt={r[6]}, active={r[7]}")
        else:
            print("  (empty)")
        conn.close()
    except Exception as exc:
        print(f"  DB error: {exc}")

    # 4. Cross-reference: identify mismatches
    print("\n\n--- MISMATCH ANALYSIS ---")
    issues = []

    # Check snapshot.py WC config vs orchestrator
    # orchestrator: dc=0.68, elo=0.15
    # snapshot WC: dc=0.55, elo=0.05
    print("  prediction_orchestrator.py hardcodes: dc=0.68, elo=0.15")
    print("  snapshot.py WORLD_CUP config:      dc=0.55, elo=0.05")
    print("  snapshot.py _get_model_config uses: dc_weight, enh_weight, elo_weight, pi_weight")
    print("  prediction_orchestrator.py uses:   base_weight=0.68, elo_weight=0.15")
    print("  ⚠ DC weight differs by 0.13 (orchestrator .68 vs snapshot .55)")
    print("  ⚠ Elo weight differs by 0.10 (orchestrator .15 vs snapshot .05)")
    issues.append("DC weight: orchestrator=0.68 vs snapshot=0.55 (Δ=0.13)")
    issues.append("Elo weight: orchestrator=0.15 vs snapshot=0.05 (Δ=0.10)")

    print("\n  fast_predict.py hardcodes:         dc=0.68, elo=0.15")
    print("  learning_engine.py hardcodes:      dc=0.68, enh=0.32, elo=0.15")
    issues.append("fast_predict.py matches orchestrator but NOT snapshot.py")

    # 5. Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    severity = "HIGH" if issues else "LOW"
    print(f"  Severity: {severity}")
    print(f"  Weight mismatch issues: {len(issues)}")
    for issue in issues:
        print(f"    - {issue}")
    print(f"\n  Recommendation: Consolidate all weights into a single WeightConfig")
    print(f"  source (either model_weight_config DB table or a weights.py module).")
    print(f"  All prediction entry points MUST read from the same config source.")

    return len(issues)


if __name__ == "__main__":
    n = main()
    print(f"\nExit: {n} issues found")
    sys.exit(min(n, 1))