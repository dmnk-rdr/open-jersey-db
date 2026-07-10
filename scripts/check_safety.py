#!/usr/bin/env python3
"""Public-safety scan for open-jersey-db.

This repository is **public**. This gate blocks any commit or pull request that
would leak content that must never appear in an open, identity-only jersey
database:

  * secrets — API keys, private keys, access tokens, passwords
  * affiliate-network identifiers, tracking params and deeplinks (AWIN /
    Tradedoubler / Impact). The DB stays **identity-only** and never carries
    commercial/affiliate data
  * internal infrastructure — private IPs, internal hostnames
  * personal e-mail addresses other than the project contact

It runs in CI on every push and pull request (see
`.github/workflows/validate.yml`) and, optionally, as a local pre-commit hook
(`.githooks/pre-commit`). Pure standard library — no dependencies.

Usage:
    check_safety.py                 # scan all tracked text files
    check_safety.py FILE [FILE...]  # scan the given files (used by the git hook)
    check_safety.py --selftest      # verify the rules catch known-bad strings

Escape hatch: append a trailing `# safety: allow` comment to a specific line if
you are certain a match is a false positive (use sparingly, and never for real
secrets or affiliate data).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTACT_EMAIL = "info@dmnkrdr.com"
ALLOW_MARK = "safety: allow"

# This scanner necessarily contains the very tokens it looks for, so it must not
# scan itself. Add other rule-bearing files here if needed.
SELF_ALLOW = {"scripts/check_safety.py"}

# Only inspect text formats used in this repo.
SCAN_EXT = {".yaml", ".yml", ".json", ".py", ".md", ".cff", ".txt", ".sh", ".cfg", ".ini"}

# Rules are assignment/artifact-oriented so they match leaked *data*, not prose
# (e.g. the word "password" in the ODbL licence text must not trip the scan).
RULES: list[tuple[str, re.Pattern[str]]] = [
    ("private-key",
     re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
    ("secret-assignment",
     re.compile(r"(?i)\b(?:api[_-]?key|secret|passwd|password|access[_-]?token"
                r"|auth[_-]?token|client[_-]?secret)\b\s*[:=]\s*['\"]?\S")),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("bearer-token", re.compile(r"(?i)\bbearer\s+[a-z0-9._\-]{20,}")),
    # Affiliate networks / tracking artifacts (never legitimate identity data).
    # NOTE: brand names that can be real manufacturers (e.g. Fanatics) are NOT
    # banned — only unambiguous network/tracking tokens.
    ("affiliate-awin", re.compile(r"(?i)\bawin\b|awin1\.com|\bawinmid\b|\bawinaffid\b")),
    ("affiliate-tradedoubler", re.compile(r"(?i)\btradedoubler\b|\btduid\b")),
    ("affiliate-tracking",
     re.compile(r"(?i)\bclickref\b|\bdeeplink\b|prf\.hn|impact-?radius")),
    ("affiliate-url-param",
     re.compile(r"(?i)[?&](?:awc|tduid|clickref|ranmid|raneaid|siteid)=")),
    ("internal-ip",
     re.compile(r"\b(?:10\.0\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}"
                r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b")),
    ("internal-host",
     re.compile(r"(?i)\bhome-01\b|panel\.dmnk|\bschlundtech\b|\.home\.rieder\.network")),
]

EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def tracked_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout
    return [ROOT / p for p in out.splitlines() if p]


def scan_line(line: str) -> list[str]:
    """Return the labels of all rules that fire on a line (respecting allow)."""
    if ALLOW_MARK in line:
        return []
    hits = [label for label, rx in RULES if rx.search(line)]
    for m in EMAIL.finditer(line):
        if m.group(0).lower() != CONTACT_EMAIL:
            hits.append("foreign-email")
    return hits


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    rel = path.relative_to(ROOT).as_posix() if path.is_absolute() else path.as_posix()
    if rel in SELF_ALLOW or path.suffix.lower() not in SCAN_EXT:
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
        return []
    findings = []
    for n, line in enumerate(text.splitlines(), 1):
        for label in scan_line(line):
            findings.append((n, label, line.strip()[:120]))
    return findings


def selftest() -> int:
    bad = [
        "api_key: sk_live_0123456789abcdef",
        "password = hunter2secret",
        'deeplink: "https://www.awin1.com/cread.php?awinmid=1234&awinaffid=567"',
        "url: https://track.example.com/c?tduid=abc123",
        "note: see clickref in the feed",
        "host: 10.0.1.63",
        "contact home-01 for details",
        "AKIAIOSFODNN7EXAMPLE is the key",
        "someone@example.com submitted this",
    ]
    good = [
        "manufacturer: adidas",
        "name: Los Angeles Rams",
        "main_sponsor: Deutsche Telekom",
        "gtins:\n  - '4099803281231'",
        "This project reports security issues to " + CONTACT_EMAIL + ".",
        "The ODbL text mentions the word password in prose.",
        "continue_token = response.get('continue')",  # not a *secret* assignment
    ]
    ok = True
    for s in bad:
        if not any(scan_line(l) for l in s.splitlines()):
            print(f"SELFTEST FAIL — not caught: {s!r}", file=sys.stderr); ok = False
    for s in good:
        if any(scan_line(l) for l in s.splitlines()):
            hits = {lbl for l in s.splitlines() for lbl in scan_line(l)}
            print(f"SELFTEST FAIL — false positive {hits}: {s!r}", file=sys.stderr); ok = False
    print("✓ selftest passed" if ok else "✗ selftest failed")
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    targets = [Path(a) for a in argv[1:]] if len(argv) > 1 else tracked_files()
    findings: list[str] = []
    for path in targets:
        for n, label, snippet in scan_file(path):
            rel = path.relative_to(ROOT).as_posix() if path.is_absolute() and ROOT in path.parents else str(path)
            findings.append(f"  {rel}:{n}  [{label}]  {snippet}")
    if findings:
        print(f"\n✗ public-safety scan: {len(findings)} forbidden match(es):\n", file=sys.stderr)
        print("\n".join(findings), file=sys.stderr)
        print("\nThis repository is public. Remove secrets, affiliate/tracking data, "
              "internal hosts or foreign e-mails before committing.\n"
              "False positive? Append '# safety: allow' to the line (use sparingly).",
              file=sys.stderr)
        return 1
    print("✓ public-safety scan clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
