#!/usr/bin/env python3
"""Generate a baseline kit catalog: home + away for every team.

Gives consumer sites real content (jersey pages) before product feeds arrive —
no GTINs or prices, those come from feeds later. source=community. Idempotent:
existing kit files (curated or richer) are never overwritten.
"""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
TEAMS = ROOT / "data" / "teams" / "football"
KITS = ROOT / "data" / "kits" / "football"

CLUB_SEASON = "2025/26"
NATIONAL_SEASON = "2024"
KIT_TYPES = ["home", "away"]


def dump(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(doc, fh, allow_unicode=True, sort_keys=False)


def main() -> int:
    created = 0
    for tp in sorted(TEAMS.rglob("*.yaml")):
        team = yaml.safe_load(tp.open(encoding="utf-8"))
        slug, league, typ = team["slug"], team.get("league"), team["type"]
        season = NATIONAL_SEASON if typ == "national" else CLUB_SEASON
        group = league or "national"

        for kit_type in KIT_TYPES:
            path = KITS / group / slug / f"{season.replace('/', '-')}-{kit_type}.yaml"
            if path.exists():
                continue  # keep curated/example kits untouched
            dump(path, {
                "team": slug, "sport": "football", "league": league,
                "season": season, "kit_type": kit_type,
                "manufacturer": None, "main_sponsor": None,
                "gtins": [], "aliases": [], "source": "community",
            })
            created += 1

    print(f"✓ generated {created} kits")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
