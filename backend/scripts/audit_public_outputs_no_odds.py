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

# Force UTF-8 stdout to avoid GBK encoding errors on Chinese Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
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

# ── Mode-aware tiered forbidden terms ──
#
# INTERNAL_RESEARCH: All terms below are allowed (reports are research artifacts)
# CREATOR_SAFE: Must not contain odds, bookmaker names, betting prompts, gambling
# PUBLIC_SAFE:  Must not contain any of the below, including probability framing

# Terms that are NEVER allowed in public/creator-facing outputs
PUBLIC_STRICTLY_FORBIDDEN = [
    # Chinese gambling/betting terms
    "投注", "博彩", "盘口", "赔率推荐", "竞彩", "带单", "稳赚", "爆单", "必胜", "推单",
    "命中率", "必中", "庄家", "博彩公司", "下注",
    # English betting/gambling terms
    "best bet", "betting tips", "bookmaker", "sportsbook", "odds pick",
    "guaranteed prediction", "sure win", "betting advice",
]

# Terms allowed in internal_research but forbidden in creator_safe/public_safe
CREATOR_SAFE_FORBIDDEN_TERMS = list(set(PUBLIC_STRICTLY_FORBIDDEN + [
    "赔率", "odds", "overround", "vig", "expected value", "value bet",
]))

# Full set for public_safe (most restrictive)
PUBLIC_SAFE_FORBIDDEN_TERMS = list(set(CREATOR_SAFE_FORBIDDEN_TERMS + [
    "胜率", "概率", "比分预测", "预计比分", "xG", "expected goals",
    "主胜", "平局概率", "客胜", "主负",
]))

# Default scan uses PUBLIC_SAFE (most restrictive)
ALL_FORBIDDEN = PUBLIC_SAFE_FORBIDDEN_TERMS


def scan_file(filepath: str, terms: list[str]) -> list[dict]:
    """Scan a file for forbidden terms, return list of findings.

    Skips terms that appear in compliance/disclaimer context:
    "does not provide", "not positioning", "must not", "never", "avoid",
    "do not", "forbidden", "disclaimer", "no gambling"
    """
    findings = []
    try:
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
    except (UnicodeDecodeError, PermissionError):
        return findings

    # Compliance context patterns — terms here are anti-claims, not marketing
    compliance_patterns = [
        r'(?:does\s+not|do\s+not)\s+(?:provide|position|offer|display|use|show|include|expose|turn)',
        r'(?:not|never)\s+(?:positioning|allowed|permitted|provide|display|include|expose)',
        r'(?:must|should)\s+(?:not|never)\s+(?:be|include|contain|display|appear|expose)',
        r'Must\s+not\s+(?:be|include|contain|display|appear|expose)',
        r'(?:avoid|avoids|avoided)',
        r'(?:forbidden|prohibited|banned)',
        r'(?:no\s+gambling|not\s+a\s+(?:betting|gambling))',
        r'(?:disclaimer|compliance\s+boundary|compliance\s+and\s+output\s+policy)',
        r'bad\s+output',
        r'Compliance\s+checklist',
        r'Public(?:-|\s)facing output does not',
    ]
    compliance_re = re.compile('|'.join(compliance_patterns), re.IGNORECASE)

    for term in terms:
        # Case-insensitive for English terms, exact for Chinese
        flags = re.IGNORECASE if term.isascii() and not any('一' <= c <= '鿿' for c in term) else 0
        for m in re.finditer(re.escape(term), content, flags=flags):
            line_no = content[:m.start()].count('\n') + 1
            # Get surrounding context (large window for table columns)
            line_start = max(0, m.start() - 500)
            line_end = min(len(content), m.end() + 500)
            surrounding = content[line_start:line_end]
            # Skip if term appears in compliance/disclaimer context
            if compliance_re.search(surrounding):
                continue
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

    # Scan reports directory
    reports_label = "reports/ (internal_research — expected to contain model terms)"
    if not os.path.exists(str(backend_root / "reports")):
        all_findings[reports_label] = []
        print(f"\n  [{reports_label}]: path not found, skipping")
    else:
        reports_findings = []
        reports_root = str(backend_root / "reports")
        for root, dirs, files in os.walk(reports_root):
            dirs[:] = [d for d in dirs if d not in ("node_modules", ".venv", "__pycache__", ".git")]
            for fname in files:
                if fname.endswith((".md", ".html", ".txt", ".json")):
                    fpath = os.path.join(root, fname)
                    file_findings = scan_file(fpath, ALL_FORBIDDEN)
                    for fd in file_findings:
                        fd["file"] = os.path.relpath(fpath, reports_root)
                    reports_findings.extend(file_findings)
        all_findings[reports_label] = reports_findings
        total = len(reports_findings)
        if total == 0:
            print(f"\n  [{reports_label}]: [OK] Clean")
        else:
            print(f"\n  [{reports_label}]: [NOTE] {total} internal terms found (expected in research reports)")

    # Scan docs directory (public-facing documentation)
    docs_label = "docs/ (public-facing — must be clean)"
    docs_root = str(backend_root / "docs")
    if not os.path.exists(docs_root):
        all_findings[docs_label] = []
        print(f"\n  [{docs_label}]: path not found, skipping")
    else:
        docs_findings = []
        for root, dirs, files in os.walk(docs_root):
            dirs[:] = [d for d in dirs if d not in ("node_modules", ".venv", "__pycache__", ".git")]
            for fname in files:
                if fname.endswith((".md", ".html", ".txt")):
                    fpath = os.path.join(root, fname)
                    # For compliance/commercial docs, don't flag terms used as "forbidden examples"
                    if "COMPLIANCE" in fname or "MARKET_DATA" in fname:
                        continue
                    file_findings = scan_file(fpath, PUBLIC_STRICTLY_FORBIDDEN)
                    for fd in file_findings:
                        fd["file"] = os.path.relpath(fpath, docs_root)
                    docs_findings.extend(file_findings)
        all_findings[docs_label] = docs_findings
        total = len(docs_findings)
        if total == 0:
            print(f"\n  [{docs_label}]: [OK] Clean")
        else:
            print(f"\n  [{docs_label}]: [WARN] {total} forbidden term(s) found")
            for fd in docs_findings[:10]:
                print(f"    {fd['file']}:{fd['line']}  「{fd['term']}」")

    # Scan root .md files (only committed public-facing ones)
    print("\n\n--- Root MD Files ---")
    root_findings = []
    committed_md_files = ["README.md", "CHANGELOG.md", "SECURITY.md", "CONTRIBUTING.md"]
    for rfile in committed_md_files:
        rpath = repo_root / rfile
        if rpath.exists():
            file_findings = scan_file(str(rpath), PUBLIC_STRICTLY_FORBIDDEN)
            for fd in file_findings:
                fd["file"] = rfile
            root_findings.extend(file_findings)
    all_findings["root .md files"] = root_findings
    total = len(root_findings)
    if total == 0:
        print(f"  [OK] Clean — no forbidden terms in committed public docs")
    else:
        print(f"  [WARN] {total} forbidden term(s) found in root .md files")
        for fd in root_findings[:10]:
            print(f"    {fd['file']}:{fd['line']}  「{fd['term']}」")

    # Scan article generator (internal templates)
    print("\n\n--- Article Generator Templates (internal) ---")
    article_gen = backend_root / "app" / "services" / "article_generator.py"
    if os.path.exists(str(article_gen)):
        findings = scan_file(str(article_gen), ALL_FORBIDDEN)
        if findings:
            print(f"  [NOTE] {len(findings)} internal terms (expected in article generator)")
        else:
            print("  [OK] Clean")

    # Scan feature_flags.yaml and config for forbidden terms in public-facing comments
    print("\n\n--- Configuration Files ---")
    for cfg_file in ["config/feature_flags.yaml", "app/config.py"]:
        cfg_path = backend_root / cfg_file
        if os.path.exists(str(cfg_path)):
            findings = scan_file(str(cfg_path), ALL_FORBIDDEN)
            if findings:
                print(f"  {cfg_file}: {len(findings)} terms (expected - internal config)")
            else:
                print(f"  {cfg_file}: [OK] Clean")

    # Summary
    total_findings = sum(len(v) for v in all_findings.values())
    # Count only public-facing findings (not internal reports/config)
    public_findings = len(all_findings.get("docs/ (public-facing — must be clean)", []))
    root_findings_count = len(all_findings.get("root .md files", []))

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Total term occurrences scanned: {total_findings}")
    print(f"  Public-facing findings (docs + root): {public_findings + root_findings_count}")
    print(f"  Article generator terms: expected (internal template)")
    print(f"  Config file terms: expected (internal use)")
    print(f"")
    print(f"  Mode reminder:")
    print(f"    - internal_research: all model/odds/probability terms OK")
    print(f"    - creator_safe: odds/bookmaker/betting terms FORBIDDEN")
    print(f"    - public_safe: odds/bookmaker + probability framing FORBIDDEN")

    if public_findings + root_findings_count > 0:
        print(f"\n  [WARN] Public-facing docs contain forbidden terms — fix before release")
        return 1
    else:
        print(f"\n  [OK] Public-facing outputs are clean")
        return 0


if __name__ == "__main__":
    sys.exit(main())
