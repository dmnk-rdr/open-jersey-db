#!/usr/bin/env python3
"""Diff: deutsche Ligen laut Wikipedia-Saisonartikel gegen die Liga-Zuordnung in open-jersey-db.

Warum ueberhaupt eine dritte Quelle, wo `check_german_leagues.py` schon OpenLigaDB abfragt:
OpenLigaDB traegt zuverlaessig nur die obersten drei Ligen. Ab Liga 4 ist es crowd-sourced
und praktisch leer — `regio-bayern` lieferte fuer 2026/27 vier von neunzehn Vereinen und eine
Tabelle ohne eine einzige Zeile, Nord/Nordost/West/Suedwest gibt es fuer die Saison gar nicht.
Zudem wechselt der Liga-Shortcut dort von Saison zu Saison (`rl-bayern` 2012 -> `regio-bayern`
2026, `rlno`/`rlno_n` parallel 2025), ein fest verdrahtetes Mapping bricht also jaehrlich.
Genau unterhalb der 3. Liga hat die Zuordnung deshalb gedriftet, ohne dass etwas anschlug:
in der Regionalliga Bayern standen zwei laengst abgestiegene Vereine, drei Aufsteiger fehlten.

Quelle ist der deutsche Wikipedia-Saisonartikel, gelesen ueber die MediaWiki-API. Extrahiert
wird NICHT aus gerenderten Tabellen, sondern aus der Vorlage `{{Fußballtabelle/Zeile|…|Verein=…}}`
— ein benanntes Feld statt freier Zellen. Das ist der Unterschied zwischen "liest richtig" und
"liest halb": ein Tabellen-Scraper liefert im Fehlerfall keine Fehlermeldung, sondern eine
kuerzere, falsche Liste, und ein Diff dagegen sieht aus wie ein Haufen echter Ligawechsel.

Die Artikeltitel werden aus der Saison ABGELEITET ("Fußball-Regionalliga Bayern 2026/27"),
nicht je Jahr gepflegt — der Rollover kostet damit keine Konfigurationsaenderung.

Read-only: schreibt nichts, gibt nur den Diff aus. Exit 1, sobald eine Liga abweicht oder
nicht verwertbar gelesen wurde.

    python3 scripts/check_wikipedia_leagues.py                 # alle Ligen, laufende Saison
    python3 scripts/check_wikipedia_leagues.py --season 2026   # andere Saison
    python3 scripts/check_wikipedia_leagues.py regionalliga-bayern 3-liga
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "teams" / "football"

WIKI_API = "https://de.wikipedia.org/w/api.php"
# Wikimedia weist Anfragen ohne aussagekraeftigen User-Agent mit HTTP 403 ab — inklusive
# Kontaktadresse, so verlangt es die Wikimedia-Etikette fuer automatisierte Zugriffe.
UA = {"User-Agent": "trikotscout-league-check/1.0 (https://trikotscout.com; info@dmnkrdr.com)"}
REQUEST_DELAY = 0.5

# Liga-Slug -> Artikeltitel-Schablone. `{s}` = Saison in Wikipedia-Schreibweise ("2026/27").
LEAGUES = {
    "bundesliga": "Fußball-Bundesliga {s}",
    "2-bundesliga": "2. Fußball-Bundesliga {s}",
    "3-liga": "3. Fußball-Liga {s}",
    "regionalliga-nord": "Fußball-Regionalliga Nord {s}",
    "regionalliga-nordost": "Fußball-Regionalliga Nordost {s}",
    "regionalliga-west": "Fußball-Regionalliga West {s}",
    "regionalliga-suedwest": "Fußball-Regionalliga Südwest {s}",
    "regionalliga-bayern": "Fußball-Regionalliga Bayern {s}",
}

# Marker hinter dem Vereinsnamen in der Tabellenvorlage: (N)eu, (A)ufsteiger, (M)eister,
# (P)okalsieger, (R)elegation, (U) — teils kombiniert ("M, P") oder mit Pfeil ("R↓").
MARKER = re.compile(r"\s*\((?:[NAMPRU](?:\s*[,/]\s*[NAMPRU])*)\s*[↑↓]?\)\s*$")


def season_label(start_year: int) -> str:
    """2026 -> '2026/27'. Wikipedia benennt die Saison nach ihrem Startjahr, zweistellig hinten."""
    return f"{start_year}/{(start_year + 1) % 100:02d}"


def current_season(today: dt.date | None = None) -> int:
    """Saisonstart im Juli — bis Juni zaehlt noch die im Vorjahr begonnene Saison."""
    today = today or dt.date.today()
    return today.year if today.month >= 7 else today.year - 1


def fetch_wikitext(title: str) -> str | None:
    """Wikitext des Artikels; None, wenn es den Artikel nicht gibt."""
    query = urllib.parse.urlencode(
        {"action": "parse", "page": title, "prop": "wikitext", "format": "json"}
    )
    last: Exception | None = None
    for attempt in range(3):
        try:
            request = urllib.request.Request(f"{WIKI_API}?{query}", headers=UA)
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.load(response)
            # "missingtitle" heisst: Artikel existiert nicht (Liga in der Saison nicht
            # gespielt, oder Titelschema geaendert). Alles andere ist ein echter Fehler.
            if "error" in data:
                if data["error"].get("code") == "missingtitle":
                    return None
                raise RuntimeError(data["error"].get("code", "unbekannt"))
            return data["parse"]["wikitext"]["*"]
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Wikipedia nicht erreichbar: {type(last).__name__}")


def _templates(text: str, name: str) -> list[str]:
    """Rumpf jeder Verwendung von {{name…}}, ueber balancierte Klammern statt Regex.

    Die Zeilen enthalten selbst wieder Vorlagen ({{FN}}, {{gestiegen}}); ein nicht-gieriges
    `\\{\\{.*?\\}\\}` bricht an der ERSTEN inneren `}}` ab und schneidet den Vereinsnamen mittendrin
    ab. Genau daran ist die erste Fassung gescheitert.
    """
    out = []
    for match in re.finditer(r"\{\{\s*" + re.escape(name) + r"\b", text):
        i = match.end()
        depth = 1
        while i < len(text) and depth:
            if text.startswith("{{", i):
                depth += 1
                i += 2
            elif text.startswith("}}", i):
                depth -= 1
                i += 2
            else:
                i += 1
        out.append(text[match.end() : i - 2])
    return out


def _split_params(body: str) -> list[str]:
    """Vorlagen-Parameter an den `|` der OBERSTEN Ebene trennen (innere Vorlagen ignorieren)."""
    parts, depth, buf = [], 0, []
    i = 0
    while i < len(body):
        if body.startswith("{{", i) or body.startswith("[[", i):
            depth += 1
            buf.append(body[i : i + 2])
            i += 2
        elif body.startswith("}}", i) or body.startswith("]]", i):
            depth -= 1
            buf.append(body[i : i + 2])
            i += 2
        elif body[i] == "|" and depth == 0:
            parts.append("".join(buf))
            buf = []
            i += 1
        else:
            buf.append(body[i])
            i += 1
    parts.append("".join(buf))
    return parts


def _clean_club(raw: str) -> str:
    """Vereinsname aus dem Feldwert: Links aufloesen, Fussnoten und Marker entfernen."""
    text = raw.strip()
    # [[Lemma|Anzeigename]] -> Anzeigename. Das ist der WICHTIGE Fall: zweite Mannschaften
    # stehen als [[FC Augsburg#Zweite Mannschaft|FC Augsburg II]] — ohne die Pipe-Aufloesung
    # bleibt entweder das Lemma (falscher Verein) oder der Abschnittstitel ("Zweite Mannschaft").
    text = re.sub(r"\[\[[^\]|]*\|([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"\[\[([^\]#|]+)(?:#[^\]|]*)?\]\]", r"\1", text)
    text = re.sub(r"<ref.*?</ref>|<ref[^>]*/>", "", text, flags=re.S)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)  # {{FN|…}}, {{gestiegen}}, …
    # Restliche Inline-Auszeichnung. Aeltere Saisonartikel haengen Fussnotenzeichen als
    # <sup>…</sup> an den Vereinsnamen ("FC Bayern München II <sup>/</sup>") — ohne das hier
    # matcht der Verein nicht mehr und taucht faelschlich als FEHLT auf.
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("'''", "").replace("''", "")
    text = " ".join(text.split())
    return MARKER.sub("", text).strip()


def clubs_from_article(text: str) -> tuple[list[str], int | None]:
    """(Vereine aus der Tabelle, Vereinszahl laut Infobox).

    Die zweite Zahl ist der unabhaengige Zeuge: sie steht als eigenes Infobox-Feld im Artikel
    und wird NICHT aus der Tabelle abgeleitet. Nur deshalb faellt ein halb gelesener
    Tabellenblock ueberhaupt auf — eine Pruefung, die sich aus derselben Extraktion speist,
    meldete bei fuenf gelesenen von zwanzig Zeilen brav "fuenf von fuenf".
    """
    clubs = []
    for body in _templates(text, "Fußballtabelle/Zeile"):
        for param in _split_params(body):
            key, _, value = param.partition("=")
            if key.strip().lower() == "verein":
                name = _clean_club(value)
                if name:
                    clubs.append(name)
                break

    expected = None
    for body in _templates(text, "Infobox Fußballsaison"):
        for param in _split_params(body):
            key, _, value = param.partition("=")
            if key.strip().lower() == "mannschaften":
                digits = re.search(r"\d+", value)
                if digits:
                    expected = int(digits.group())
                break
    return clubs, expected


def strict(s: str) -> str:
    """Normalisierung OHNE Gattungswoerter zu streichen — wird ZUERST probiert.

    Reihenfolge wie in `check_foreign_leagues.py`: erst exakt, dann grosszuegig. Streicht man
    sofort grosszuegig, kollabieren verschiedene Vereine auf denselben Schluessel.
    """
    s = s.lower().strip()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss"), ("é", "e"), ("è", "e")):
        s = s.replace(a, b)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split())


# Gattungswoerter und Rechtsformen, die zwischen zwei deutschen Vereinen nie unterscheiden.
#
# Was hier bewusst NICHT drinsteht, ist wichtiger als was drinsteht:
#
# `ii` nicht — sonst faellt "Hannover 96 II" auf "Hannover 96", und der Diff meldet den
# Zweitligisten als in die Regionalliga gewechselt. Zweite Mannschaften sind eigene Eintraege.
#
# `hsc` (und andere seltene Kuerzel) nicht — zusammen mit dem Streichen reiner Zahl-Token
# wurde aus "HSC Hannover" und "Hannover 96" derselbe Schluessel "hannover". Beides fiel im
# ersten Lauf nur auf, weil `_collisions()` es gemessen hat; die Diff-Ausgabe selbst sah
# plausibel aus. Deshalb bleiben Zahlen ebenfalls stehen: die Gruendungsjahre sind bei uns
# haeufig das EINZIGE unterscheidende Token.
GENERIC = {
    "fc", "sc", "sv", "tsv", "tsg", "fsv", "ssv", "spvgg", "vfl", "vfb", "vfr", "bsc", "sg",
    "tus", "djk", "sf", "sfr", "spfr", "sportfreunde", "fussballclub", "fussballverein",
    "sportverein", "fussball", "club", "verein",
}


def norm(s: str) -> str:
    """Grosszuegig: Gattungswoerter weg, alles Unterscheidende bleibt stehen.

    Faengt Schreibweisen wie "1. FC Koeln" vs. "FC Köln" ab. Faengt bewusst NICHT
    "SV Eintracht Trier 05" vs. "SV Eintracht Trier" — das ist ein Alias und gehoert in die
    YAML des Vereins, nicht in eine Regel, die nebenbei fremde Vereine verschmilzt.
    """
    return " ".join(t for t in strict(s).split() if t not in GENERIC)


def load_db() -> dict[str, dict]:
    """slug -> {name, league, aliases} fuer alle Fussballvereine."""
    teams = {}
    for path in DB.rglob("*.yaml"):
        text = path.read_text(encoding="utf-8")
        name = re.search(r"^name:\s*(.+)$", text, re.M)
        league = re.search(r"^league:\s*(.+)$", text, re.M)
        aliases = (
            re.findall(r"^-\s*(.+)$", text.split("aliases:")[1].split("\n\n")[0], re.M)
            if "aliases:" in text
            else []
        )
        teams[path.stem] = {
            "name": name.group(1).strip() if name else path.stem,
            "league": league.group(1).strip() if league else path.parent.name,
            "aliases": [a.strip() for a in aliases if not a.strip().startswith("{")],
        }
    return teams


def _collisions(db: dict[str, dict]) -> list[tuple[str, list[str]]]:
    """Vereine, die unter `norm()` auf denselben Schluessel fallen.

    `norm()` streicht Gattungswoerter und Zahlen — das kann zwei echte Vereine verschmelzen,
    und dann zeigt der Diff stillschweigend auf den falschen. Deshalb wird die Regel gemessen,
    statt ihr zu glauben; Treffer werden als WARNUNG ausgegeben.
    """
    buckets: dict[str, list[str]] = {}
    for slug, team in db.items():
        buckets.setdefault(norm(team["name"]), []).append(team["name"])
    return sorted((k, sorted(v)) for k, v in buckets.items() if len(v) > 1 and k)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("leagues", nargs="*", help=f"Liga-Slugs (Default: alle). Bekannt: {', '.join(LEAGUES)}")
    parser.add_argument("--season", type=int, default=None, help="Startjahr der Saison, z. B. 2026")
    args = parser.parse_args()

    unknown = [x for x in args.leagues if x not in LEAGUES]
    if unknown:
        print(f"Unbekannte Liga-Slugs: {', '.join(unknown)}", file=sys.stderr)
        return 2

    season = args.season if args.season is not None else current_season()
    wanted = args.leagues or list(LEAGUES)
    label = season_label(season)
    print(f"Quelle: de.wikipedia.org — Saison {label}\n")

    db = load_db()
    collisions = _collisions(db)
    if collisions:
        print(f"WARNUNG: {len(collisions)} Namenskollision(en) unter norm() — "
              f"Zuordnung dieser Vereine ist mehrdeutig:")
        for key, names in collisions:
            print(f"   {key:28} <- {', '.join(names)}")
        print()

    strict_lookup: dict[str, str] = {}
    loose_lookup: dict[str, str] = {}
    for slug, team in db.items():
        for key in [strict(team["name"]), strict(slug)] + [strict(a) for a in team["aliases"]]:
            if key:
                strict_lookup.setdefault(key, slug)
        for key in [norm(team["name"]), norm(slug)] + [norm(a) for a in team["aliases"]]:
            if key:
                loose_lookup.setdefault(key, slug)

    exit_code = 0
    for league in wanted:
        title = LEAGUES[league].format(s=label)
        time.sleep(REQUEST_DELAY)
        try:
            text = fetch_wikitext(title)
        except RuntimeError as exc:
            print(f"### {league}: {exc}")
            exit_code = 1
            continue
        if text is None:
            print(f"### {league}: Artikel „{title}“ existiert nicht — MANUELL pruefen\n")
            exit_code = 1
            continue

        clubs, expected = clubs_from_article(text)

        # Plausibilitaetssperre. Ein Diff gegen eine halb gelesene Liste waere die
        # gefaehrlichste Ausgabe dieses Skripts: er saehe aus wie echte Ligawechsel.
        if expected is None:
            print(f"### {league}: Infobox nennt keine Vereinszahl — kein unabhaengiger Zeuge "
                  f"fuer die Vollstaendigkeit. Kein Diff, bleibt MANUELL.\n")
            exit_code = 1
            continue
        if len(clubs) != expected:
            print(f"### {league}: Teilnehmerliste NICHT VERWERTBAR — {len(clubs)} Vereine "
                  f"gelesen, Infobox nennt {expected}. Kein Diff (er waere Rauschen), "
                  f"bleibt MANUELL.\n")
            exit_code = 1
            continue

        seen, wrong, missing = set(), [], []
        for club in clubs:
            slug = strict_lookup.get(strict(club)) or loose_lookup.get(norm(club))
            if slug is None:
                missing.append(club)
                continue
            seen.add(slug)
            if db[slug]["league"] != league:
                wrong.append((club, db[slug]["league"], slug))
        extra = [(s, t["name"]) for s, t in db.items() if t["league"] == league and s not in seen]

        held = sum(1 for t in db.values() if t["league"] == league)
        print(f"### {league} ({title}) — Kader {len(clubs)}, DB fuehrt {held}")
        for name, have, slug in wrong:
            print(f"   WECHSEL   {name:34} DB: {have:22} [{slug}]")
        for name in missing:
            print(f"   FEHLT     {name:34} (nicht in open-jersey-db)")
        for slug, name in extra:
            print(f"   ZUVIEL    {name:34} steht in {league}, nicht im Kader [{slug}]")
        if wrong or missing or extra:
            exit_code = 1
        else:
            print("   deckungsgleich")
        print()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
