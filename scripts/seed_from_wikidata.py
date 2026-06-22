#!/usr/bin/env python3
"""Seed/extend teams from Wikidata (CC0 → ODbL-compatible).

Pulls the current clubs of the top-5 European football leagues and writes
data/teams/football/<league>/<slug>.yaml. Idempotent and curation-safe:

  - New clubs  → full record (name, country, founded, aliases from altLabels, wikidata id).
  - Existing curated files are NOT overwritten; only missing `founded` / `wikidata`
    are filled in. Curated names/aliases stay.

Roster source (in order of reliability):
  1. Participants (P1923) of the league's most recent *populated* season. To keep
     each SPARQL query light (Wikidata times out on correlated season sub-queries),
     we first list populated seasons + start dates cheaply, pick the latest per
     league in Python, then fetch only those seasons' participants.
  2. Fallback for leagues whose seasons don't carry participants (e.g. Serie A):
     clubs linked via P118, minus dissolved clubs (P576).

Match-to-existing is by slug or by an existing team's normalized name/alias, so a
Wikidata label variant never creates a duplicate club.

Stdlib + PyYAML only. Re-run any time.
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
TEAMS = ROOT / "data" / "teams" / "football"

ENDPOINT = "https://query.wikidata.org/sparql"
UA = "open-jersey-db/0.1 (https://github.com/dmnk-rdr/open-jersey-db)"

# Wikidata league item -> our league slug (all verified)
LEAGUES = {
    "Q82595": "bundesliga",
    "Q9448": "premier-league",
    "Q324867": "la-liga",
    "Q15804": "serie-a",
    "Q13394": "ligue-1",
}

# Step 1 — cheap: which seasons have participants, and when did they start.
Q_SEASONS = """
SELECT ?league ?season ?start WHERE {
  VALUES ?league { %s }
  ?season wdt:P3450 ?league ; wdt:P580 ?start ; wdt:P1923 [] .
}
"""

# Common SELECT/labels tail for the two roster queries below.
_FIELDS = """
  (SAMPLE(?de) AS ?nameDe) (SAMPLE(?en) AS ?nameEn) (SAMPLE(?iso) AS ?country)
  (MIN(YEAR(?inception)) AS ?founded) (SAMPLE(?league) AS ?league)
  (GROUP_CONCAT(DISTINCT ?alt; separator="|") AS ?alts)
"""
_OPTIONALS = """
  OPTIONAL { ?club rdfs:label ?de FILTER(LANG(?de)="de") }
  OPTIONAL { ?club rdfs:label ?en FILTER(LANG(?en)="en") }
  OPTIONAL { ?club wdt:P17 ?c. ?c wdt:P297 ?iso. }
  OPTIONAL { ?club wdt:P571 ?inception. }
  OPTIONAL { ?club skos:altLabel ?alt FILTER(LANG(?alt) IN ("de","en")) }
"""

# Step 2a — participants of specific (already chosen) seasons. Some leagues (e.g.
# the German Bundesliga) link a "men's football team" entity rather than the club
# itself; resolve those to the parent club via P361 so we get the real item (with
# founded/country). Clubs linked directly (e.g. Premier League) pass through.
Q_PARTICIPANTS = """
SELECT ?club %s WHERE {
  VALUES ?season { %s }
  ?season wdt:P3450 ?league ; wdt:P1923 ?participant .
  OPTIONAL { ?participant wdt:P31 wd:Q103229495 ; wdt:P361 ?parent . }
  BIND(COALESCE(?parent, ?participant) AS ?club)
  FILTER NOT EXISTS { ?club wdt:P576 ?dissolved }
  %s
}
GROUP BY ?club
"""

# Step 2b — fallback: clubs via P118 (for leagues without season participants).
Q_P118 = """
SELECT ?club %s WHERE {
  VALUES ?league { %s }
  ?club wdt:P118 ?league ; wdt:P31/wdt:P279* wd:Q476028 .
  FILTER NOT EXISTS { ?club wdt:P576 ?dissolved }
  %s
}
GROUP BY ?club
"""

UMLAUTS = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}

# Generic football-name tokens that don't identify a club on their own. Used only
# to find the *distinctive* token of a name for duplicate detection (e.g. the city).
GENERIC = {
    "fc", "sc", "sv", "vfl", "vfb", "tsg", "ssc", "ac", "as", "us", "afc", "cf",
    "rc", "rcd", "ud", "sd", "club", "calcio", "balompie", "fussball", "verein",
    "borussia", "real", "athletic", "atletico", "united", "city", "hellas",
}


def distinctive_tokens(name: str) -> set[str]:
    return {t for t in norm(name).split()
            if len(t) >= 4 and t not in GENERIC and not t.isnumeric()}


def slugify(name: str) -> str:
    s = name.lower()
    for a, b in UMLAUTS.items():
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def norm(s: str) -> str:
    """Match key mirroring the consumer's Normalizer: lowercase, .- -> space."""
    s = s.lower().replace(".", " ").replace("-", " ")
    return re.sub(r"\s+", " ", s).strip()


def fetch(sparql: str, retries: int = 4) -> list[dict]:
    data = urllib.parse.urlencode({"query": sparql, "format": "json"}).encode()
    req = urllib.request.Request(ENDPOINT, data=data,
                                 headers={"User-Agent": UA,
                                          "Accept": "application/sparql-results+json"})
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.load(resp)["results"]["bindings"]
        except Exception as exc:  # noqa: BLE001 — retry transient 429/5xx/timeouts
            if attempt == retries:
                raise
            wait = 3 * attempt
            print(f"  query attempt {attempt} failed ({exc}); retrying in {wait}s…",
                  file=sys.stderr)
            time.sleep(wait)
    return []


def val(row: dict, key: str):
    return row[key]["value"] if key in row and row[key]["value"] != "" else None


def tail(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]


def clean_aliases(raw: str, name: str) -> list[str]:
    out, seen = [], {norm(name)}
    for a in (raw or "").split("|"):
        a = a.strip().lower()
        k = norm(a)
        if len(a) < 2 or a.isnumeric() or k in seen:
            continue
        seen.add(k)
        out.append(a)
    return sorted(out)


def index_existing() -> tuple[dict[str, Path], dict[str, Path], dict[str, Path]]:
    by_slug, by_name, by_token = {}, {}, {}
    for p in TEAMS.rglob("*.yaml"):
        doc = yaml.safe_load(p.open(encoding="utf-8"))
        by_slug[doc["slug"]] = p
        by_name[norm(doc["name"])] = p
        for a in doc.get("aliases") or []:
            by_name.setdefault(norm(a), p)
        for t in distinctive_tokens(doc["name"]):
            by_token.setdefault(t, p)
        for a in doc.get("aliases") or []:
            for t in distinctive_tokens(a):
                by_token.setdefault(t, p)
    return by_slug, by_name, by_token


def collect() -> list[dict]:
    vals = " ".join(f"wd:{q}" for q in LEAGUES)
    seasons = fetch(Q_SEASONS % vals)

    # Latest populated season per league (compare ISO date strings).
    latest: dict[str, tuple[str, str]] = {}
    for r in seasons:
        lq, start, sq = tail(val(r, "league")), val(r, "start"), tail(val(r, "season"))
        if lq not in latest or start > latest[lq][0]:
            latest[lq] = (start, sq)

    rows: list[dict] = []
    if latest:
        season_vals = " ".join(f"wd:{sq}" for _, sq in latest.values())
        rows += fetch(Q_PARTICIPANTS % (_FIELDS, season_vals, _OPTIONALS))

    missing = [q for q, slug in LEAGUES.items() if q not in latest]
    if missing:
        print(f"  no season participants for {[LEAGUES[q] for q in missing]} — "
              f"P118 fallback", file=sys.stderr)
        rows += fetch(Q_P118 % (_FIELDS, " ".join(f"wd:{q}" for q in missing), _OPTIONALS))
    return rows


def main() -> int:
    try:
        rows = collect()
    except Exception as exc:  # noqa: BLE001
        print(f"Wikidata query failed: {exc}", file=sys.stderr)
        return 1

    by_slug, by_name, by_token = index_existing()
    n_new = n_merged = 0

    def find_existing(name: str) -> Path | None:
        hit = by_slug.get(slugify(name)) or by_name.get(norm(name))
        if hit:
            return hit
        # distinctive-token match catches curated clubs whose Wikidata name differs
        # ("1. FC Heidenheim" vs "1. FC Heidenheim 1846").
        for t in distinctive_tokens(name):
            if t in by_token:
                return by_token[t]
        return None

    for r in rows:
        qid = tail(val(r, "club"))
        name = val(r, "nameDe") or val(r, "nameEn")
        if not name:
            continue
        league = LEAGUES.get(tail(val(r, "league") or ""))
        if not league:
            continue
        country = (val(r, "country") or "").upper() or None
        founded = int(val(r, "founded")) if val(r, "founded") else None

        target = find_existing(name)
        if target:  # existing curated club — fill gaps only
            doc = yaml.safe_load(target.open(encoding="utf-8"))
            changed = False
            if not doc.get("founded") and founded:
                doc["founded"] = founded
                changed = True
            if not doc.get("wikidata"):
                doc["wikidata"] = qid
                changed = True
            if changed:
                yaml.safe_dump(doc, target.open("w", encoding="utf-8"),
                               allow_unicode=True, sort_keys=False)
                n_merged += 1
            continue

        slug = slugify(name)
        doc = {
            "slug": slug, "name": name, "sport": "football", "type": "club",
            "league": league, "country": country,
            # altLabels + the bare distinctive core (e.g. "arsenal") so shop short
            # forms match even when the canonical name carries a prefix ("FC Arsenal").
            "aliases": clean_aliases(
                "|".join(filter(None, [val(r, "alts"), *distinctive_tokens(name)])),
                name),
            "founded": founded, "wikidata": qid,
        }
        path = TEAMS / league / f"{slug}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        yaml.safe_dump(doc, path.open("w", encoding="utf-8"),
                       allow_unicode=True, sort_keys=False)
        by_slug[slug] = path
        by_name[norm(name)] = path
        n_new += 1

    print(f"✓ Wikidata seed: {n_new} new clubs, {n_merged} existing enriched "
          f"({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
