#!/usr/bin/env python3
"""Enrich existing teams with founded / city / stadium from Wikidata (CC0 → ODbL-ok).

For every team YAML that carries a `wikidata` QID, this fills MISSING fields only:

  - founded : earliest YEAR of inception (P571)
  - city    : label of headquarters location (P159)
  - stadium : label of home venue (P115) — ONLY when the club has exactly one
              P115 value, so we never guess between a current and a historical
              ground. Ambiguous cases stay empty (the consumer renders adaptively).

Curation-safe: never overwrites a value that is already present in the YAML
(so hand-verified entries like the uhlsport/Kempa clubs are untouched).

Stdlib + PyYAML only. Idempotent — re-run any time.

Usage:
  python3 scripts/enrich_from_wikidata.py [--dry-run] [--sport football]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
TEAMS = ROOT / "data" / "teams"
API = "https://www.wikidata.org/w/api.php"
UA = "open-jersey-db/0.1 (https://github.com/dmnk-rdr/open-jersey-db)"
BATCH = 50

# Wikidata "instance of" (P31) types that count as a human settlement, so we only
# ever publish a real city — never a club HQ building or training-ground hamlet.
SETTLEMENT = {
    "Q515",       # city
    "Q1549591",   # big city
    "Q486972",    # human settlement
    "Q3957",      # town
    "Q532",       # village
    "Q15284",     # municipality
    "Q747074",    # comune of Italy
    "Q484170",    # commune of France
    "Q22865",     # kreisfreie Stadt (Germany)
    "Q262166",    # municipality of Germany (Gemeinde)
    "Q1093829",   # city of Germany
    "Q42744322",  # urban municipality of Germany
    "Q2074737",   # locality
    "Q702492",    # urban area
    "Q188509",    # suburb
    "Q5119",      # capital city
    "Q1637706",   # megacity
    "Q1208802",   # ciudad (Spain)
    "Q2039348",   # localidad
    "Q1763234",   # municipality of Spain
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


def _entities(qids: list[str], props: str, languages: str | None = None) -> dict:
    ents: dict = {}
    for i in range(0, len(qids), BATCH):
        params = {"action": "wbgetentities", "ids": "|".join(qids[i : i + BATCH]), "props": props}
        if languages:
            params["languages"] = languages
        ents.update(_get(params).get("entities", {}))
        time.sleep(0.3)
    return ents


def _claim_year(claims: dict, pid: str) -> int | None:
    years = []
    for c in claims.get(pid, []):
        val = (c.get("mainsnak", {}).get("datavalue") or {}).get("value") or {}
        t = val.get("time")
        if t:
            neg = t.startswith("-")
            try:
                years.append(-int(t[1:5]) if neg else int(t[1:5]))
            except ValueError:
                pass
    return min(years) if years else None


def _claim_ids(claims: dict, pid: str) -> list[str]:
    ids = []
    for c in claims.get(pid, []):
        val = (c.get("mainsnak", {}).get("datavalue") or {}).get("value") or {}
        if val.get("id"):
            ids.append(val["id"])
    return ids


def collect(qids: list[str]) -> dict[str, dict]:
    """qid -> {founded:int|None, city:str|None, stadium:str|None}.

    Uses the MediaWiki wbgetentities API (stable, unaffected by WDQS outages):
    first the club claims (P571 founded, P159 city, P115 venue), then a second
    pass to resolve the referenced city/venue items to human labels.
    """
    ents = _entities(qids, props="claims")

    founded: dict[str, int | None] = {}
    city_id: dict[str, str] = {}
    venue_ids: dict[str, list[str]] = {}
    ref: set[str] = set()

    for qid in qids:
        claims = ents.get(qid, {}).get("claims", {})
        founded[qid] = _claim_year(claims, "P571")
        cids = _claim_ids(claims, "P159")
        if cids:
            city_id[qid] = cids[0]
            ref.add(cids[0])
        vids = _claim_ids(claims, "P115")
        venue_ids[qid] = vids
        ref.update(vids)

    # Resolve labels AND the P31 type of every referenced item in one pass, so we
    # can label venues and sanity-check that a city candidate is really a settlement.
    refents = _entities(sorted(ref), props="labels|claims", languages="de|en") if ref else {}

    def label(item_id: str) -> str | None:
        lbls = refents.get(item_id, {}).get("labels", {})
        for lang in ("de", "en"):
            if lang in lbls:
                return lbls[lang]["value"]
        return None

    def is_settlement(item_id: str) -> bool:
        p31 = _claim_ids(refents.get(item_id, {}).get("claims", {}), "P31")
        return bool(set(p31) & SETTLEMENT)

    out: dict[str, dict] = {}
    for qid in qids:
        vlabels = {label(v) for v in venue_ids.get(qid, [])} - {None}
        cid = city_id.get(qid)
        out[qid] = {
            "founded": founded.get(qid),
            # only accept a city that Wikidata actually types as a settlement
            "city": label(cid) if cid and is_settlement(cid) else None,
            # only an unambiguous single home venue → no guessing current vs. historical
            "stadium": next(iter(vlabels)) if len(vlabels) == 1 else None,
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sport", default=None, help="limit to one sport subdir")
    args = ap.parse_args()

    base = TEAMS / args.sport if args.sport else TEAMS
    files = sorted(base.rglob("*.yaml"))

    # slug/QID index of teams that (a) have a wikidata id and (b) miss a field.
    by_qid: dict[str, list[tuple[Path, dict]]] = defaultdict(list)
    for f in files:
        doc = yaml.safe_load(f.read_text()) or {}
        qid = doc.get("wikidata")
        if not qid:
            continue
        if doc.get("founded") and doc.get("city") and doc.get("stadium"):
            continue  # already complete
        by_qid[qid].append((f, doc))

    qids = list(by_qid)
    if not qids:
        print("Nothing to enrich (no wikidata ids with missing fields).")
        return
    print(f"Querying Wikidata for {len(qids)} teams …")
    data = collect(qids)

    changed = 0
    for qid, entries in by_qid.items():
        wd = data.get(qid, {})
        for f, doc in entries:
            added = []
            for field in ("founded", "city", "stadium"):
                if not doc.get(field) and wd.get(field):
                    doc[field] = wd[field]
                    added.append(f"{field}={wd[field]}")
            if added:
                changed += 1
                print(f"  {f.relative_to(ROOT)}: {', '.join(added)}")
                if not args.dry_run:
                    f.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False))

    print(f"{'[dry-run] ' if args.dry_run else ''}Enriched {changed} team file(s).")


if __name__ == "__main__":
    main()
