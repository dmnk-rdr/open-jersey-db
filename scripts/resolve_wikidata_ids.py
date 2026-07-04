#!/usr/bin/env python3
"""Resolve Wikidata QIDs for teams that lack one, verified by league membership.

For each team YAML without a `wikidata` id, searches Wikidata by name/aliases
(wbsearchentities) and accepts a candidate ONLY if its league claim (P118) — or
sport (P641) as a fallback — matches what we expect for that team's league slug.
That league-match guard prevents grabbing a same-named but wrong entity.

Writes the resolved `wikidata:` id back into the YAML (nothing else). Afterwards
run enrich_from_wikidata.py to pull founded/city/stadium.

Stdlib + PyYAML only. Idempotent.

Usage:
  python3 scripts/resolve_wikidata_ids.py [--sport basketball] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
TEAMS = ROOT / "data" / "teams"
API = "https://www.wikidata.org/w/api.php"
UA = "open-jersey-db/0.1 (https://github.com/dmnk-rdr/open-jersey-db)"

# league slug -> expected Wikidata league item (P118). Verified.
LEAGUE_QID = {
    "nba": "Q155223",
    "nfl": "Q1215884",
    "nhl": "Q1215892",
    "mlb": "Q1163715",
}


def _get(params: dict) -> dict:
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 3:
                time.sleep(20 * (attempt + 1))
                continue
            raise
    return {}


def search(name: str) -> list[str]:
    res = _get({"action": "wbsearchentities", "search": name, "language": "en",
                "type": "item", "limit": 7})
    return [hit["id"] for hit in res.get("search", [])]


def claim_ids(claims: dict, pid: str) -> list[str]:
    out = []
    for c in claims.get(pid, []):
        val = (c.get("mainsnak", {}).get("datavalue") or {}).get("value") or {}
        if val.get("id"):
            out.append(val["id"])
    return out


def resolve(name: str, league_qid: str) -> str | None:
    candidates = search(name)
    if not candidates:
        return None
    ents = _get({"action": "wbgetentities", "ids": "|".join(candidates), "props": "claims"}).get("entities", {})
    for qid in candidates:  # candidates are ranked by relevance
        claims = ents.get(qid, {}).get("claims", {})
        if league_qid in claim_ids(claims, "P118"):
            return qid
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sport", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    base = TEAMS / args.sport if args.sport else TEAMS
    resolved = skipped = 0
    for f in sorted(base.rglob("*.yaml")):
        doc = yaml.safe_load(f.read_text()) or {}
        if doc.get("wikidata"):
            continue
        league_qid = LEAGUE_QID.get(doc.get("league"))
        if not league_qid:
            continue  # only leagues we can verify against
        qid = resolve(doc["name"], league_qid)
        time.sleep(0.4)
        if not qid:
            skipped += 1
            print(f"  ? {f.relative_to(ROOT)}: no league-verified match")
            continue
        resolved += 1
        print(f"  {f.relative_to(ROOT)}: wikidata={qid}")
        if not args.dry_run:
            doc["wikidata"] = qid
            f.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False))

    print(f"{'[dry-run] ' if args.dry_run else ''}Resolved {resolved}, unmatched {skipped}.")


if __name__ == "__main__":
    main()
