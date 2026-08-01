#!/usr/bin/env python3
"""Auslandsliga-Check OHNE football-data.org-Key.

Quelle: die Wikipedia-Saisonartikel 2026/27 (CC-BY-SA, wie die Ausruester-/Kit-Historie im
Projekt ohnehin schon). Gelesen wird der Abschnitt "Stadiums and locations" — dort steht je
Verein eine Tabellenzeile `! scope="row" | [[Arsenal F.C.|Arsenal]]`, also die vollstaendige
Teilnehmerliste der Saison.

Read-only: gibt nur den Diff gegen open-jersey-db aus, schreibt nichts.
"""
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / 'data' / 'teams' / 'football'
# Slug -> (Wikipedia-Artikel, erwartete Vereinszahl der Liga).
# Die Zahl ist eine PLAUSIBILITAETSSPERRE, kein Detail: die Wikitext-Tabellen sind je Artikel
# unterschiedlich gebaut, und wenn der Extraktor danebengreift, liefert er nicht "nichts",
# sondern eine halbe, falsche Liste (La Liga: 5 statt 20 Vereine, darunter zwei Zweitligisten).
# Ein Diff gegen so eine Liste sieht aus wie ein Haufen echter Ligawechsel und waere die
# gefaehrlichste Sorte Fehlalarm — deshalb wird bei Abweichung gar kein Diff ausgegeben.
PAGES = {
    'premier-league': ('2026–27 Premier League', 20),
    'la-liga': ('2026–27 La Liga', 20),
    'serie-a': ('2026–27 Serie A', 20),
    'ligue-1': ('2026–27 Ligue 1', 18),
}
API = 'https://en.wikipedia.org/w/api.php'
# Wikipedia weist Requests ohne aussagekraeftigen User-Agent mit 403 ab.
UA = {'User-Agent': 'trikotscout-league-rollover/1.0 (https://trikotscout.com)'}


def _get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30)


def strict(s):
    """Normalisierung OHNE Gattungswoerter zu streichen.

    Wird ZUERST probiert, weil das aggressive norm() unten sonst kollidiert: es streicht "FC",
    wodurch "Paris FC" zu "paris" wird — und das zeigt in unserem Alias-Bestand auf Paris
    Saint-Germain. Der Verein galt dadurch als "nicht im Kader", obwohl er drinsteht. Erst
    exakt vergleichen, dann grosszuegig.
    """
    s = s.lower().strip()
    for a, b in (('ä', 'ae'), ('ö', 'oe'), ('ü', 'ue'), ('ß', 'ss'), ('é', 'e'), ('è', 'e'),
                 ('á', 'a'), ('í', 'i'), ('ó', 'o'), ('ú', 'u'), ('ñ', 'n'), ('ç', 'c')):
        s = s.replace(a, b)
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', s).split())


def norm(s):
    s = s.lower().strip()
    for a, b in (('ä', 'ae'), ('ö', 'oe'), ('ü', 'ue'), ('ß', 'ss'), ('é', 'e'),
                 ('è', 'e'), ('á', 'a'), ('í', 'i'), ('ó', 'o'), ('ú', 'u'), ('ñ', 'n'), ('ç', 'c')):
        s = s.replace(a, b)
    s = re.sub(r'\b(fc|cf|ac|as|ss|us|sc|afc|ssc|calcio|club|de|deportivo|futbol|football)\b', ' ', s)
    s = re.sub(r'[^a-z0-9]+', ' ', s)
    return ' '.join(s.split())


# La Liga nennt den Abschnitt anders als die uebrigen drei.
WANTED_SECTIONS = ('Personnel and kits', 'Personnel and sponsorship')


def wiki_section(page, want=WANTED_SECTIONS):
    q = urllib.parse.urlencode({'action': 'parse', 'page': page, 'prop': 'sections', 'format': 'json'})
    with _get(f'{API}?{q}') as r:
        secs = json.load(r)['parse']['sections']
    idx = next((s['index'] for s in secs if s['line'] in want), None)
    if idx is None:
        return ''
    q = urllib.parse.urlencode({'action': 'parse', 'page': page, 'prop': 'wikitext',
                                'format': 'json', 'section': idx})
    with _get(f'{API}?{q}') as r:
        return json.load(r)['parse']['wikitext']['*']


def clubs_from(text):
    """Erste Zelle je Tabellenzeile des Abschnitts "Personnel and kits".

    Der Abschnitt ist in allen vier Artikeln eine schlichte `wikitable` mit dem Vereinsnamen
    in Spalte 1 — mal als Klartext, mal als Wikilink. Bewusst nicht der Abschnitt
    "Stadiums and locations": der beginnt mit einer Positionskarte, deren Marker auch Staedte
    (z. B. "London") enthalten, die keine Vereine sind.
    """
    out = []
    for block in text.split('|-')[1:]:
        for line in block.strip().split('\n'):
            line = line.strip()
            if not line.startswith('|') or line.startswith('|}'):
                continue
            cell = line[1:].strip()
            cell = re.sub(r'\{\{[^{}]*\}\}', '', cell)
            m = re.search(r'\[\[([^\]]+)\]\]', cell)
            if m:
                cell = m.group(1).split('|')[-1]
            cell = re.sub(r'<ref.*', '', cell, flags=re.S).strip()
            if cell:
                out.append(cell)
            break
    return out


def load_db():
    teams = {}
    for f in DB.rglob('*.yaml'):
        t = f.read_text(encoding='utf-8')
        name = re.search(r'^name:\s*(.+)$', t, re.M)
        league = re.search(r'^league:\s*(.+)$', t, re.M)
        aliases = re.findall(r'^-\s*(.+)$', t.split('aliases:')[1].split('\n\n')[0], re.M) \
            if 'aliases:' in t else []
        teams[f.stem] = {'name': name.group(1).strip() if name else f.stem,
                         'league': league.group(1).strip() if league else f.parent.name,
                         'aliases': [a.strip() for a in aliases if not a.strip().startswith('{')]}
    return teams


def main():
    db = load_db()
    lookup, strict_lookup = {}, {}
    for slug, t in db.items():
        for k in [strict(t['name']), strict(slug)] + [strict(a) for a in t['aliases']]:
            if k:
                strict_lookup.setdefault(k, slug)
        for k in [norm(t['name']), norm(slug)] + [norm(a) for a in t['aliases']]:
            if k:
                lookup.setdefault(k, slug)

    exit_code = 0
    for league, (page, expected) in PAGES.items():
        wanted = clubs_from(wiki_section(page))
        if len(wanted) != expected:
            print(f'\n### {league}: Teilnehmerliste NICHT VERWERTBAR — {len(wanted)} statt '
                  f'{expected} Vereinen aus "{page}" gelesen. Kein Diff (er waere Rauschen). '
                  f'Diese Liga bleibt MANUELL, bis der Extraktor sie beherrscht oder ein '
                  f'football-data.org-Key vorliegt.')
            exit_code = 1
            continue
        seen, wrong, missing = set(), [], []
        for name in wanted:
            slug = strict_lookup.get(strict(name)) or lookup.get(norm(name))
            if slug is None:
                missing.append(name)
                continue
            seen.add(slug)
            if db[slug]['league'] != league:
                wrong.append((name, db[slug]['league'], slug))
        extra = [(s, t['name']) for s, t in db.items() if t['league'] == league and s not in seen]
        print(f'\n### {league} — Wikipedia nennt {len(wanted)} Vereine, DB fuehrt '
              f'{sum(1 for t in db.values() if t["league"] == league)}')
        for name, have, slug in wrong:
            print(f'   WECHSEL   {name:32} DB: {have:22} [{slug}]')
        for name in missing:
            print(f'   FEHLT     {name:32} (nicht in open-jersey-db)')
        for slug, name in extra:
            print(f'   ZUVIEL    {name:32} steht in {league}, aber nicht im Kader [{slug}]')
        if not (wrong or missing or extra):
            print('   deckungsgleich')
        else:
            exit_code = 1

    return exit_code


if __name__ == '__main__':
    sys.exit(main())
