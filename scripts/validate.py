#!/usr/bin/env python3
"""Validate open-jersey-db data.

Runs two layers:
  1. JSON Schema validation (only if the `jsonschema` package is installed).
  2. Cross-file integrity checks that schemas can't express:
       - slug uniqueness + slug == filename
       - kit.team references an existing team
       - kit.sport matches the referenced team's sport
       - GTIN check-digit (mod-10) validity
       - filesystem path matches sport/league/type

Exit code is non-zero on any error, so it doubles as a CI gate.
Depends only on PyYAML; jsonschema is optional.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SCHEMA = ROOT / "schema"

GTIN_RE = re.compile(r"^(\d{8}|\d{12,14})$")

errors: list[str] = []


def err(path: Path, msg: str) -> None:
    errors.append(f"{path.relative_to(ROOT)}: {msg}")


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def gtin_valid(gtin: str) -> bool:
    """GTIN-8/12/13/14 mod-10 check-digit validation."""
    if not GTIN_RE.match(gtin):
        return False
    digits = [int(c) for c in gtin]
    check = digits[-1]
    body = digits[:-1][::-1]
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(body))
    return (10 - total % 10) % 10 == check


def load_schema_validator(name: str):
    """Return a callable(doc)->errors using jsonschema, or None if unavailable."""
    try:
        import jsonschema
    except ModuleNotFoundError:
        return None
    schema = json.loads((SCHEMA / name).read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    return lambda doc: [e.message for e in validator.iter_errors(doc)]


# Einzelwörter, die für sich genommen KEINEN Verein identifizieren: sie sind
# Bestandteil vieler Vereinsnamen. Als eigenständiger Alias reißen sie fremde
# Vereine an sich — "Hull City" landete so bei Manchester City, "West Bromwich
# Albion" bei West Ham, "Inter Milan" bei AC Milan. Zwei Sorten:
#   - Namensbausteine (city/united/town/albion/…) und Ortszusätze (west/saint/…)
#   - Kürzel, die echte Wörter sind ("im" trifft jedes deutsche "… im Trikot …")
# Der lange, eindeutige Alias ("manchester city") bleibt selbstverständlich erlaubt.
GENERIC_ALIASES = {
    "fc", "sc", "ac", "cf", "afc", "im", "i m",
    "united", "city", "town", "albion", "wanderers", "rovers", "county", "athletic",
    "real", "sporting", "club", "deportivo", "sociedad", "atletico", "atlético",
    "inter", "milan", "olympique", "stade", "racing", "sport", "union",
    "saint", "germain", "west", "east", "north", "south",
    "national", "team", "jordan",
}


def main() -> int:
    team_validator = load_schema_validator("team.schema.json")
    kit_validator = load_schema_validator("kit.schema.json")
    if team_validator is None:
        print("note: jsonschema not installed — running integrity checks only "
              "(schema enforced in CI).", file=sys.stderr)

    teams: dict[str, dict] = {}

    # --- Teams ---
    for path in sorted((DATA / "teams").rglob("*.yaml")):
        doc = load_yaml(path)
        if not isinstance(doc, dict):
            err(path, "not a YAML mapping")
            continue
        if team_validator:
            for m in team_validator(doc):
                err(path, f"schema: {m}")
        for alias in doc.get("aliases") or []:
            if str(alias).strip().lower() in GENERIC_ALIASES:
                err(path, f"alias '{alias}' identifies no single club — it is a name "
                          f"component many clubs share; use the full name instead")
        slug = doc.get("slug")
        if slug and slug != path.stem:
            err(path, f"slug '{slug}' != filename '{path.stem}'")
        if slug in teams:
            err(path, f"duplicate team slug '{slug}'")
        elif slug:
            teams[slug] = doc
        # path convention: data/teams/<sport>/<league|national>/<slug>.yaml
        parts = path.relative_to(DATA / "teams").parts
        if len(parts) == 3:
            sport_dir, group_dir, _ = parts
            if doc.get("sport") and doc["sport"] != sport_dir:
                err(path, f"sport '{doc['sport']}' != path '{sport_dir}'")
            expected = "national" if doc.get("type") == "national" else doc.get("league")
            if expected and expected != group_dir:
                err(path, f"league/type folder '{group_dir}' != expected '{expected}'")
        else:
            err(path, "expected path data/teams/<sport>/<league|national>/<slug>.yaml")

    # --- Kits ---
    for path in sorted((DATA / "kits").rglob("*.yaml")):
        doc = load_yaml(path)
        if not isinstance(doc, dict):
            err(path, "not a YAML mapping")
            continue
        if kit_validator:
            for m in kit_validator(doc):
                err(path, f"schema: {m}")
        team = doc.get("team")
        if team and team not in teams:
            err(path, f"unknown team '{team}' (no data/teams entry)")
        elif team:
            t = teams[team]
            if doc.get("sport") and t.get("sport") and doc["sport"] != t["sport"]:
                err(path, f"sport '{doc['sport']}' != team sport '{t['sport']}'")
        for gtin in doc.get("gtins") or []:
            if not gtin_valid(str(gtin)):
                err(path, f"invalid GTIN '{gtin}' (format or check-digit)")
        if doc.get("source") == "manufacturer" and not doc.get("verified_by"):
            err(path, "source=manufacturer requires 'verified_by'")

    if errors:
        print(f"\n✗ {len(errors)} validation error(s):\n", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(f"✓ valid — {len(teams)} teams, "
          f"{sum(1 for _ in (DATA / 'kits').rglob('*.yaml'))} kits")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
