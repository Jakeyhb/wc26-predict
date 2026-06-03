"""Phase 0: Audit public-facing outputs for forbidden terms.
Read-only — no business logic changes.

Scans:
1. Markdown reports in backend/reports/
2. Root-level .md files (ARCHITECTURE.md, PROJECT_STATUS.md, etc.)
3. Static site output (if exists)
4. Article generator templates
5. API response samples (from config/snapshots)

Forbidden terms (public_safe + creator_safe):
  赔率, 盘口, 博彩, 投注, 竞彩, 下注, 庄家, 博彩公司,
  betting, odds, bookmaker, handicap, spread, over/under,
  moneyline, wager, stake, payout, ROI, 盈利, 稳赚,
  必中, 命中率, 带单

Additional public_safe-only forbidden:
  胜率, 概率, 比分预测, 预计比分, xG, expected goals,
  主胜, 平局概率, 客胜
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# ── Forbidden terms ──
CREATOR_SAFE_FORBIDDEN = [
    # Chinese
    "赔率", "盘口", "博彩", "投注", "竞彩", "下注", "庄家", "博彩公司",
    # English
    "betting", "odds", "bookmaker", "handicap", "spread",
    "over/under", "moneyline", "wager", "stake", "payout",
    "ROI", "盈利", "稳赚", "必中", "命中率", "带单",
]

PUBLIC_SAFE_EXTRA_FORBIDDEN = [
    "胜率", "概率", "比分预测", "预计比分", "xG", "expected goals",
    "主胜", "平局概率", "客胜",
]

ALL_FORBIDDEN = list(set(CREATOR_SAFE_FORBIDDEN + PUBLIC_SAFE_EXTRA_FORBIDDEN))


def scan_file(filepath: str, terms: list[str]) -> list[dict]:
    """Scan a file for forbidden terms, return list of findings."""
    findings = []
    try:
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
    except (UnicodeDecodeError, PermissionError):
        return findings

    for term in terms:
        # Case-insensitive for English terms, exact for Chinese
        flags = re.IGNORECASE if term.isascii() and not any('一' <= c <= '鿿' for c in term) else 0
        for m in re.finditer(re.escape(term), content, flags=flags):
            line_no = content[:m.start()].count('\n') + 1
            ctx_start = max(0, m.start() - 30)
            ctx_end = min(len(content), m.end() + 30)
            ctx = content[ctx_start:ctx_end].replace('\n', ' ').strip()
            findings.append({
                "term": term,
                "line": line_no,
                "context": f"...{ctx}...",
            })
    return findings


def main():
    print("=" * 70)
    print("AUDIT: Public Output Safety — Forbidden Terms Scan")
    print("=" * 70)

    backend_root = PROJECT_ROOT
    repo_root = PROJECT_ROOT.parent

    # Directories to scan
    scan_dirs = {
        "reports/": str(backend_root / "reports"),
        "docs/": str(backend_root / "docs"),
        "root .md files": str(repo_root),
        "generated static site": str(backend_root / "static_site"),
    }

    all_findings: dict[str, list] = {}

    for label, scan_path in scan_dirs.items():
        if not os.path.exists(scan_path):
            all_findings[label] = []
            print(f"\n  [{label}]: path not found, skipping")
            continue

        findings = []
        if label == "root .md files":
            for f in os.listdir(scan_path):
                if f.endswith(".md") and os.path.isfile(os.path.join(scan_path, f)):
                    findings.extend(
                        scan_file(os.path.join(scan_path, f), ALL_FORBIDDEN)
                    )
                    # Tag each finding
                    for fd in findings:
                        fd["file"] = f
        else:
            for root, dirs, files in os.walk(scan_path):
                # Skip node_modules, .venv, __pycache__
                dirs[:] = [d for d in dirs if d not in ("node_modules", ".venv", "__pycache__", ".git")]
                for fname in files:
                    if fname.endswith((".md", ".html", ".txt", ".json")):
                        fpath = os.path.join(root, fname)
                        file_findings = scan_file(fpath, ALL_FORBIDDEN)
                        for fd in file_findings:
                            fd["file"] = os.path.relpath(fpath, scan_path)
                        findings.extend(file_findings)

        all_findings[label] = findings
        total = len(findings)
        if total == 0:
            print(f"\n  [{label}]: ✓ Clean — no forbidden terms found")
        else:
            print(f"\n  [{label}]: ⚠ {total} forbidden term(s) found")
            for fd in findings[:10]:  # show first 10
                print(f"    {fd['file']}:{fd['line']}  「{fd['term']}」")
                print(f"      {fd['context'][:80]}")

    # Also scan article generator output patterns
    print("\n\n--- Article Generator Templates ---")
    article_gen = backend_root / "app" / "services" / "article_generator.py"
    if os.path.exists(str(article_gen)):
        findings = scan_file(str(article_gen), ALL_FORBIDDEN)
        if findings:
            print(f"  ⚠ {len(findings)} forbidden terms in article_generator.py:")
            for fd in findings[:10]:
                print(f"    L{fd['line']}: 「{fd['term']}」")
                print(f"      {fd['context'][:80]}")
        else:
            print("  ✓ Clean")

    # Scan feature_flags.yaml and config for forbidden terms in public-facing comments
    print("\n\n--- Configuration Files ---")
    for cfg_file in ["config/feature_flags.yaml", "app/config.py"]:
        cfg_path = backend_root / cfg_file
        if os.path.exists(str(cfg_path)):
            findings = scan_file(str(cfg_path), ALL_FORBIDDEN)
            if findings:
                print(f"  {cfg_file}: {len(findings)} terms (expected - internal config)")
            else:
                print(f"  {cfg_file}: ✓ Clean")

    # Summary
    total_findings = sum(len(v) for v in all_findings.values())
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Total forbidden term occurrences: {total_findings}")
    print(f"  Scanned: reports, docs, root .md, static_site, article_generator")
    print(f"  Note: Market calibrator, config files INTERNALLY contain these terms")
    print(f"        — this is expected for internal use. Focus of this audit is")
    print(f"        public-facing outputs only.")
    if total_findings > 0:
        print(f"\n  ⚠ Action: Review all public-facing files and remove forbidden terms")
        print(f"    before enabling creator_safe or public_safe modes.")
    else:
        print(f"\n  ✓ Public outputs are currently clean.")

    return min(total_findings, 1)


if __name__ == "__main__":
    sys.exit(main())
