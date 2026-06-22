#!/usr/bin/env python3
"""One-time seed: port TrikotScout's config/teams.php into open-jersey-db.

Writes data/teams/football/<league|national>/<slug>.yaml for the 27 teams that
already existed as alias groups in TrikotScout, plus a few example kits so the
schema + pipeline have real data to chew on. Idempotent — safe to re-run.

This is the *origin* of the database; future entries arrive via PRs (manufacturers,
community) and via the feed-harvest flywheel.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# (canonical name, league, country, [aliases]) — football clubs
CLUBS = [
    ("FC Bayern München", "bundesliga", "DE", ["bayern", "bayern munich", "bayern muenchen", "fc bayern", "fcb", "fc bayern munchen"]),
    ("Borussia Dortmund", "bundesliga", "DE", ["dortmund", "bvb", "bvb 09", "borussia dortmund 09"]),
    ("RB Leipzig", "bundesliga", "DE", ["leipzig", "rb leipzig", "rasenballsport leipzig"]),
    ("Bayer 04 Leverkusen", "bundesliga", "DE", ["leverkusen", "bayer leverkusen", "bayer 04", "bayer 04 leverkusen"]),
    ("Eintracht Frankfurt", "bundesliga", "DE", ["frankfurt", "eintracht frankfurt", "sge"]),
    ("VfB Stuttgart", "bundesliga", "DE", ["stuttgart", "vfb", "vfb stuttgart"]),
    ("SC Freiburg", "bundesliga", "DE", ["freiburg", "sc freiburg"]),
    ("VfL Wolfsburg", "bundesliga", "DE", ["wolfsburg", "vfl wolfsburg"]),
    ("Borussia Mönchengladbach", "bundesliga", "DE", ["gladbach", "monchengladbach", "moenchengladbach", "borussia monchengladbach", "bmg"]),
    ("1. FC Union Berlin", "bundesliga", "DE", ["union berlin", "1 fc union berlin", "fc union berlin"]),
    ("TSG 1899 Hoffenheim", "bundesliga", "DE", ["hoffenheim", "tsg hoffenheim", "tsg 1899 hoffenheim"]),
    ("SV Werder Bremen", "bundesliga", "DE", ["werder", "werder bremen", "sv werder bremen"]),
    ("1. FSV Mainz 05", "bundesliga", "DE", ["mainz", "mainz 05", "fsv mainz 05", "1 fsv mainz 05"]),
    ("FC Augsburg", "bundesliga", "DE", ["augsburg", "fc augsburg"]),
    ("1. FC Heidenheim", "bundesliga", "DE", ["heidenheim", "fc heidenheim", "1 fc heidenheim"]),
    ("FC St. Pauli", "bundesliga", "DE", ["st pauli", "fc st pauli", "sankt pauli"]),
    ("Holstein Kiel", "bundesliga", "DE", ["kiel", "holstein kiel"]),
    ("VfL Bochum", "bundesliga", "DE", ["bochum", "vfl bochum"]),
]

# (canonical name, country, [aliases]) — football national teams.
# Erweitert für die WM 2026 (Gastgeber USA/Kanada/Mexiko + große Trikot-Nationen).
NATIONS = [
    ("Deutschland", "DE", ["deutschland", "germany", "dfb", "dfb team", "nationalmannschaft deutschland"]),
    ("Frankreich", "FR", ["frankreich", "france", "les bleus"]),
    ("Brasilien", "BR", ["brasilien", "brazil", "brasil", "selecao"]),
    ("Spanien", "ES", ["spanien", "spain", "espana", "la roja"]),
    ("England", "GB-ENG", ["england", "three lions"]),
    ("Italien", "IT", ["italien", "italy", "italia", "azzurri"]),
    ("Niederlande", "NL", ["niederlande", "netherlands", "holland", "oranje"]),
    ("Portugal", "PT", ["portugal"]),
    ("Argentinien", "AR", ["argentinien", "argentina", "albiceleste"]),
    # WM-2026-Gastgeber
    ("USA", "US", ["usa", "vereinigte staaten", "united states", "usmnt", "stars and stripes"]),
    ("Kanada", "CA", ["kanada", "canada"]),
    ("Mexiko", "MX", ["mexiko", "mexico", "el tri"]),
    # Europa
    ("Belgien", "BE", ["belgien", "belgium", "red devils", "rote teufel"]),
    ("Kroatien", "HR", ["kroatien", "croatia", "vatreni"]),
    ("Schweiz", "CH", ["schweiz", "switzerland", "suisse", "nati"]),
    ("Österreich", "AT", ["oesterreich", "osterreich", "austria"]),
    ("Dänemark", "DK", ["daenemark", "danemark", "denmark"]),
    ("Polen", "PL", ["polen", "poland", "polska"]),
    ("Serbien", "RS", ["serbien", "serbia"]),
    ("Türkei", "TR", ["tuerkei", "turkei", "turkey", "turkiye"]),
    ("Schottland", "GB-SCT", ["schottland", "scotland"]),
    ("Norwegen", "NO", ["norwegen", "norway"]),
    ("Schweden", "SE", ["schweden", "sweden"]),
    # Südamerika
    ("Uruguay", "UY", ["uruguay", "la celeste"]),
    ("Kolumbien", "CO", ["kolumbien", "colombia", "los cafeteros"]),
    ("Ecuador", "EC", ["ecuador", "la tri"]),
    # Afrika
    ("Marokko", "MA", ["marokko", "morocco", "atlas lions", "atlasloewen"]),
    ("Senegal", "SN", ["senegal", "lions of teranga"]),
    ("Ghana", "GH", ["ghana", "black stars"]),
    ("Nigeria", "NG", ["nigeria", "super eagles"]),
    ("Kamerun", "CM", ["kamerun", "cameroon", "indomitable lions"]),
    # Asien / Ozeanien
    ("Japan", "JP", ["japan", "samurai blue"]),
    ("Südkorea", "KR", ["suedkorea", "sudkorea", "south korea", "korea republic", "korea"]),
    ("Australien", "AU", ["australien", "australia", "socceroos"]),
    ("Saudi-Arabien", "SA", ["saudi-arabien", "saudi arabien", "saudi arabia"]),
]

# Example kits to exercise the schema (no fabricated GTINs — those arrive via
# manufacturer/feed contributions). source=community.
KITS = [
    dict(team="fc-bayern-muenchen", league="bundesliga", season="2024/25", kit_type="home",
         manufacturer="adidas", main_sponsor="Deutsche Telekom"),
    dict(team="borussia-dortmund", league="bundesliga", season="2024/25", kit_type="home",
         manufacturer="Puma", main_sponsor="1&1"),
    dict(team="deutschland", league=None, season="2024", kit_type="home",
         manufacturer="adidas", main_sponsor=None),
]

UMLAUTS = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}


def slugify(name: str) -> str:
    s = name.lower()
    for a, b in UMLAUTS.items():
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def dump(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(doc, fh, allow_unicode=True, sort_keys=False, default_flow_style=False)


def main() -> None:
    n_teams = n_kits = 0

    for name, league, country, aliases in CLUBS:
        slug = slugify(name)
        path = DATA / "teams" / "football" / league / f"{slug}.yaml"
        if path.exists():  # keep enriched/curated files (e.g. Wikidata ids/founded)
            continue
        dump(path, {
            "slug": slug, "name": name, "sport": "football", "type": "club",
            "league": league, "country": country, "aliases": aliases,
        })
        n_teams += 1

    for name, country, aliases in NATIONS:
        slug = slugify(name)
        path = DATA / "teams" / "football" / "national" / f"{slug}.yaml"
        if path.exists():
            continue
        dump(path, {
            "slug": slug, "name": name, "sport": "football", "type": "national",
            "league": None, "country": country, "aliases": aliases,
        })
        n_teams += 1

    for kit in KITS:
        group = kit["league"] or "national"
        season_slug = kit["season"].replace("/", "-")
        path = DATA / "kits" / "football" / group / kit["team"] / f"{season_slug}-{kit['kit_type']}.yaml"
        if path.exists():
            continue
        dump(path, {
            "team": kit["team"], "sport": "football", "league": kit["league"],
            "season": kit["season"], "kit_type": kit["kit_type"],
            "manufacturer": kit["manufacturer"], "main_sponsor": kit["main_sponsor"],
            "gtins": [], "aliases": [], "source": "community",
        })
        n_kits += 1

    print(f"✓ seeded {n_teams} teams, {n_kits} kits")


if __name__ == "__main__":
    main()
