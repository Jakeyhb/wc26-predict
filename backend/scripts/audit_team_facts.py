"""Phase 0: Fact-check audit for team tournament status consistency.

Scans reports and docs for factual errors — phrases that contradict a team's
known tournament status (qualified vs eliminated).

Usage:
    python scripts/audit_team_facts.py --check
        Scan all reports/ and docs/ files for forbidden phrases.

    python scripts/audit_team_facts.py --check-report "Some text here"
        Check a single text string for forbidden phrases.

Exit codes:
    0 — clean (no violations found)
    1 — FACT_CHECK_FAILED (one or more violations found)
"""
from __future__ import annotations

import json
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


def load_team_statuses(data_path: Path) -> dict:
    """Load team tournament status data from JSON file.

    Returns dict keyed by team_name with status and forbidden phrase lists,
    or None if the file doesn't exist.
    """
    if not data_path.exists():
        print(f"  [WARN] Team tournament status file not found: {data_path}")
        print(f"  [WARN] Skipping fact-check audit.")
        return None

    with open(data_path, encoding="utf-8") as f:
        raw = json.load(f)

    teams = raw.get("teams", {})
    global_forbidden_qualified = raw.get("FORBIDDEN_PHRASES_IF_QUALIFIED", [])
    global_forbidden_eliminated = raw.get("FORBIDDEN_PHRASES_IF_ELIMINATED", [])

    statuses = {}
    for team_name, info in teams.items():
        status = info.get("status", "")
        # Per-team forbidden lists (if any), fall back to global lists
        forbidden_if_qualified = (
            info.get("FORBIDDEN_PHRASES_IF_QUALIFIED")
            or global_forbidden_qualified
        )
        forbidden_if_eliminated = (
            info.get("FORBIDDEN_PHRASES_IF_ELIMINATED")
            or global_forbidden_eliminated
        )
        statuses[team_name] = {
            "team_name": team_name,
            "status": status,
            "FORBIDDEN_PHRASES_IF_QUALIFIED": forbidden_if_qualified,
            "FORBIDDEN_PHRASES_IF_ELIMINATED": forbidden_if_eliminated,
        }
    return statuses


def get_forbidden_phrases_for_team(team_info: dict) -> list[str]:
    """Return the list of forbidden phrases relevant to this team's status."""
    status = team_info["status"]
    if status == "qualified":
        return team_info["FORBIDDEN_PHRASES_IF_QUALIFIED"]
    elif status == "eliminated":
        return team_info["FORBIDDEN_PHRASES_IF_ELIMINATED"]
    return []


def scan_text(text: str, team_name: str, forbidden_phrases: list[str]) -> list[dict]:
    """Scan `text` for any forbidden phrases about the given team.

    Returns a list of finding dicts with keys: team, status, matched_phrase.
    Skips matches where the forbidden phrase appears after "does not",
    "is not", "are not", "was not", "were not", "avoid", etc. (i.e. it is
    being negated or discussed in a compliance/disclaimer context).
    """
    findings = []

    if not forbidden_phrases:
        return findings

    # Compliance negation patterns — if the forbidden phrase is negated
    # or discussed as something to avoid, skip it.
    negation_pattern = re.compile(
        r'(does\s+not|do\s+not|did\s+not|is\s+not|are\s+not|'
        r'was\s+not|were\s+not|will\s+not|must\s+not|should\s+not|'
        r'cannot|cannot|can\s+not|avoid|forbidden|prohibited|'
        r'must\s+never|should\s+never)',
        re.IGNORECASE,
    )

    for phrase in forbidden_phrases:
        flags = re.IGNORECASE if phrase.isascii() else 0
        for m in re.finditer(re.escape(phrase), text, flags=flags):
            # Check for negation within a reasonable window (200 chars before)
            start = max(0, m.start() - 200)
            before = text[start:m.start()].strip()
            if negation_pattern.search(before):
                continue
            findings.append({
                "team": team_name,
                "status": None,  # filled in by caller
                "matched_phrase": phrase,
            })

    return findings


def scan_file(
    filepath: str,
    team_name: str,
    forbidden_phrases: list[str],
) -> list[dict]:
    """Scan a single file for forbidden phrases about a team.

    Returns list of finding dicts with keys: team, status, matched_phrase, file, line.
    """
    findings = []
    try:
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
    except (UnicodeDecodeError, PermissionError, FileNotFoundError):
        return findings

    if not forbidden_phrases:
        return findings

    # Compliance negation patterns
    negation_pattern = re.compile(
        r'(does\s+not|do\s+not|did\s+not|is\s+not|are\s+not|'
        r'was\s+not|were\s+not|will\s+not|must\s+not|should\s+not|'
        r'cannot|cannot|can\s+not|avoid|forbidden|prohibited|'
        r'must\s+never|should\s+never)',
        re.IGNORECASE,
    )

    for phrase in forbidden_phrases:
        flags = re.IGNORECASE if phrase.isascii() else 0
        for m in re.finditer(re.escape(phrase), content, flags=flags):
            line_no = content[:m.start()].count('\n') + 1
            # Check for negation within a reasonable window (200 chars before)
            start = max(0, m.start() - 200)
            before = content[start:m.start()].strip()
            if negation_pattern.search(before):
                continue
            findings.append({
                "team": team_name,
                "status": None,  # filled in by caller
                "matched_phrase": phrase,
                "file": filepath,
                "line": line_no,
            })

    return findings


def check_report_text(text: str, team_statuses: dict) -> list[dict]:
    """Check a single text string for forbidden phrases across all teams.

    Returns list of violation dicts.
    """
    violations = []
    for team_name, team_info in team_statuses.items():
        forbidden_phrases = get_forbidden_phrases_for_team(team_info)
        if not forbidden_phrases:
            continue
        findings = scan_text(text, team_name, forbidden_phrases)
        for fd in findings:
            fd["status"] = team_info["status"]
            violations.append(fd)
    return violations


def check_files(
    directories: list[Path],
    team_statuses: dict,
) -> list[dict]:
    """Scan all files in given directories for forbidden phrases.

    Returns list of violation dicts with file/line info.
    """
    violations = []
    scanned_count = 0

    for directory in directories:
        if not directory.exists():
            continue
        for root, dirs, files in os.walk(str(directory)):
            dirs[:] = [d for d in dirs if d not in (
                "node_modules", ".venv", "__pycache__", ".git"
            )]
            for fname in files:
                if not fname.endswith((".md", ".html", ".txt", ".json")):
                    continue
                fpath = os.path.join(root, fname)
                for team_name, team_info in team_statuses.items():
                    forbidden_phrases = get_forbidden_phrases_for_team(team_info)
                    if not forbidden_phrases:
                        continue
                    findings = scan_file(fpath, team_name, forbidden_phrases)
                    for fd in findings:
                        fd["status"] = team_info["status"]
                        violations.append(fd)
                scanned_count += 1

    return violations


def main() -> int:
    print("=" * 70)
    print("AUDIT: Team Tournament Status — Fact Check")
    print("=" * 70)

    # Determine data file path (relative to project root or backend)
    data_path_candidates = [
        PROJECT_ROOT.parent / "data" / "team_tournament_status.json",
        PROJECT_ROOT / "data" / "team_tournament_status.json",
    ]
    data_path = None
    for candidate in data_path_candidates:
        if candidate.exists():
            data_path = candidate
            break
    if data_path is None:
        data_path = data_path_candidates[0]  # use default for error message

    team_statuses = load_team_statuses(data_path)
    if team_statuses is None:
        print(f"\n  [OK] No status data — skipping fact-check audit.")
        return 0

    print(f"\n  Loaded status data for {len(team_statuses)} team(s):")
    for name, info in team_statuses.items():
        print(f"    - {name}: {info['status']}")

    # ── Mode 1: Check a single text string ──
    if len(sys.argv) >= 3 and sys.argv[1] == "--check-report":
        text = sys.argv[2]
        print(f"\n  Mode: --check-report (single string)")
        print(f"  Input text: {text[:120]}{'...' if len(text) > 120 else ''}")
        print()

        violations = check_report_text(text, team_statuses)
        if violations:
            for v in violations:
                print(
                    f"  [FACT_CHECK_FAILED] Team '{v['team']}' is "
                    f"'{v['status']}' but report says: '{v['matched_phrase']}'"
                )
            print(f"\n  Result: FAILED ({len(violations)} violation(s))")
            return 1
        else:
            print(f"  [OK] No fact-check violations found.")
            return 0

    # ── Mode 2: Check files ──
    if len(sys.argv) >= 2 and sys.argv[1] == "--check":
        print(f"\n  Mode: --check (file scan)")
    else:
        print(f"\n  Mode: --check (file scan — default)")

    backend_root = PROJECT_ROOT

    # Directories to scan
    scan_dirs = [
        backend_root / "reports",
        backend_root / "docs",
    ]

    print(f"\n  Scanning directories:")
    for d in scan_dirs:
        exists = d.exists()
        print(f"    {d.relative_to(backend_root) if d.is_relative_to(backend_root) else d}: {'found' if exists else 'not found, skipping'}")

    violations = check_files(scan_dirs, team_statuses)

    print()
    if not violations:
        print("  [OK] No fact-check violations found across all files.")
    else:
        for v in violations:
            rel_path = (
                Path(v["file"]).relative_to(backend_root)
                if Path(v["file"]).is_relative_to(backend_root)
                else v["file"]
            )
            print(
                f"  [FACT_CHECK_FAILED] Team '{v['team']}' is "
                f"'{v['status']}' but report says: '{v['matched_phrase']}'"
            )
            print(f"    -> {rel_path}:{v['line']}")

    print()
    print("=" * 70)
    if violations:
        print(f"RESULT: FACT_CHECK_FAILED — {len(violations)} violation(s) found")
        return 1
    else:
        print(f"RESULT: PASS — All files fact-check clean")
        return 0


if __name__ == "__main__":
    sys.exit(main())
