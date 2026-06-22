#!/usr/bin/env python3
"""Compile data/*.yaml into deterministic dist/*.json artifacts.

Outputs:
  dist/teams.json    — all teams, sorted
  dist/kits.json     — all kits, sorted
  dist/aliases.json  — { "Canonical Name": ["alias", ...] }, a drop-in for a
                       consumer's name-normalization map (e.g. TrikotScout's
                       config('teams.aliases')).

Deterministic ordering + trailing newline keep dist/ diffs clean, so CI can
assert that committed artifacts match the source data.
Depends only on PyYAML.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DIST = ROOT / "dist"

TEAM_FIELDS = ["slug", "name", "sport", "type", "league", "country",
               "aliases", "founded", "wikidata", "logo_url"]
KIT_FIELDS = ["team", "sport", "league", "season", "kit_type", "player_name",
              "manufacturer", "main_sponsor", "colorway", "gtins", "aliases",
              "source", "verified_by", "notes"]


def load_all(subdir: str) -> list[dict]:
    docs = []
    for path in (DATA / subdir).rglob("*.yaml"):
        with path.open(encoding="utf-8") as fh:
            docs.append(yaml.safe_load(fh))
    return docs


def ordered(doc: dict, fields: list[str]) -> dict:
    return {f: doc[f] for f in fields if f in doc}


def write_json(name: str, obj) -> None:
    DIST.mkdir(exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False)
    (DIST / name).write_text(text + "\n", encoding="utf-8")


def main() -> None:
    teams = sorted(load_all("teams"),
                   key=lambda t: (t.get("sport", ""), t.get("type", ""),
                                  t.get("league") or "", t["slug"]))
    kits = sorted(load_all("kits"),
                  key=lambda k: (k.get("sport", ""), k["team"],
                                 k["season"], k["kit_type"]))

    write_json("teams.json", [ordered(t, TEAM_FIELDS) for t in teams])
    write_json("kits.json", [ordered(k, KIT_FIELDS) for k in kits])

    aliases = {t["name"]: sorted(set(t.get("aliases") or []))
               for t in sorted(teams, key=lambda t: t["name"])}
    write_json("aliases.json", aliases)

    print(f"✓ built dist/ — {len(teams)} teams, {len(kits)} kits, "
          f"{len(aliases)} alias groups")


if __name__ == "__main__":
    main()
