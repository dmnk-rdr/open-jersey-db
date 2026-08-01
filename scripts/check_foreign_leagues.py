#!/usr/bin/env python3
"""Auslandsliga-Check: Kader der europaeischen Topligen gegen die Liga-Zuordnung in open-jersey-db.

Zwei Quellen, in dieser Reihenfolge:

1. **football-data.org** (bevorzugt) — braucht einen kostenlosen API-Key in
   `../.football-data.key` (BEWUSST ausserhalb beider Git-Repos, damit er nicht committebar
   ist). Liefert die Kader sauber strukturiert.
2. **Wikipedia-Saisonartikel** (Fallback ohne Key) — CC-BY-SA, wie die Ausruester-Historie im
   Projekt ohnehin. Die Wikitext-Tabellen sind je Artikel unterschiedlich gebaut; greift der
   Extraktor daneben, liefert er nicht "nichts", sondern eine halbe, falsche Liste (La Liga:
   5 statt 20 Vereine, darunter zwei Zweitligisten). Ein Diff dagegen sieht aus wie ein Haufen
   echter Ligawechsel und waere die gefaehrlichste Sorte Fehlalarm — deshalb die
   Plausibilitaetssperre ueber die erwartete Kadergroesse, die fuer BEIDE Quellen gilt.

Read-only: gibt nur den Diff aus, schreibt nichts. Exit 1, sobald eine Liga abweicht oder
nicht verwertbar gelesen wurde.
"""
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / 'data' / 'teams' / 'football'
KEY_FILE = ROOT.parent / '.football-data.key'

# Slug -> (football-data-Code, Wikipedia-Artikel, erwartete Vereinszahl)
LEAGUES = {
    'premier-league': ('PL', '2026–27 Premier League', 20),
    'la-liga': ('PD', '2026–27 La Liga', 20),
    'serie-a': ('SA', '2026–27 Serie A', 20),
    'ligue-1': ('FL1', '2026–27 Ligue 1', 18),
}
SEASON = 2026

WIKI_API = 'https://en.wikipedia.org/w/api.php'
WIKI_UA = {'User-Agent': 'trikotscout-league-rollover/1.0 (https://trikotscout.com)'}
WIKI_SECTIONS = ('Personnel and kits', 'Personnel and sponsorship')


def api_key():
    """Key aus der Datei — wird NIE ausgegeben, auch nicht in Fehlermeldungen."""
    try:
        key = KEY_FILE.read_text(encoding='utf-8').strip()
    except OSError:
        return None
    return key or None


def _get(url, headers):
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30)


def clubs_from_api(code, key):
    url = f'https://api.football-data.org/v4/competitions/{code}/teams?season={SEASON}'
    try:
        with _get(url, {'X-Auth-Token': key}) as r:
            data = json.load(r)
    except Exception as exc:                        # noqa: BLE001
        # Nur den Fehlertyp zeigen: eine ausfuehrliche Exception koennte die URL samt
        # mitgeschicktem Header in den Output tragen.
        print(f'   (football-data {code} nicht erreichbar: {type(exc).__name__})')
        return []
    # BEIDE Schreibweisen zurueckgeben. Der Kurzname allein reicht nicht: football-data nennt
    # RC Deportivo La Coruña schlicht "Deportivo" — ein Wort, das sich Deportivo Alavés,
    # Deportivo Toluca und Deportivo Riestra teilen. Als Alias waere es mehrdeutig, und
    # `validate.py` weist es zu Recht ab. Also matcht der Vergleich unten zusaetzlich gegen
    # den vollen Namen, statt den Katalog fuer den Abgleich aufzuweichen.
    return [(t.get('shortName') or t.get('name'), t.get('name') or t.get('shortName'))
            for t in data.get('teams', [])]


def clubs_from_wikipedia(page):
    q = urllib.parse.urlencode({'action': 'parse', 'page': page, 'prop': 'sections', 'format': 'json'})
    with _get(f'{WIKI_API}?{q}', WIKI_UA) as r:
        secs = json.load(r)['parse']['sections']
    idx = next((s['index'] for s in secs if s['line'] in WIKI_SECTIONS), None)
    if idx is None:
        return []
    q = urllib.parse.urlencode({'action': 'parse', 'page': page, 'prop': 'wikitext',
                                'format': 'json', 'section': idx})
    with _get(f'{WIKI_API}?{q}', WIKI_UA) as r:
        text = json.load(r)['parse']['wikitext']['*']

    out = []
    for block in text.split('|-')[1:]:
        for line in block.strip().split('\n'):
            line = line.strip()
            if not line.startswith('|') or line.startswith('|}'):
                continue
            cell = re.sub(r'\{\{[^{}]*\}\}', '', line[1:].strip())
            m = re.search(r'\[\[([^\]]+)\]\]', cell)
            if m:
                cell = m.group(1).split('|')[-1]
            cell = re.sub(r'<ref.*', '', cell, flags=re.S).strip()
            if cell:
                out.append((cell, cell))
            break
    return out


def strict(s):
    """Normalisierung OHNE Gattungswoerter zu streichen — wird ZUERST probiert.

    Das grosszuegige norm() unten streicht "FC", wodurch "Paris FC" zu "paris" wird — und das
    zeigt in unserem Alias-Bestand auf Paris Saint-Germain. Der Verein galt dadurch als "nicht
    im Kader", obwohl er drinsteht. Erst exakt vergleichen, dann grosszuegig.
    """
    s = s.lower().strip()
    for a, b in (('ä', 'ae'), ('ö', 'oe'), ('ü', 'ue'), ('ß', 'ss'), ('é', 'e'), ('è', 'e'),
                 ('á', 'a'), ('í', 'i'), ('ó', 'o'), ('ú', 'u'), ('ñ', 'n'), ('ç', 'c')):
        s = s.replace(a, b)
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', s).split())


def norm(s):
    s = strict(s)
    # Rechtsform-/Gattungspraefixe, die zwischen zwei Vereinen nie unterscheiden. Die
    # spanischen (rc/rcd/ud/cd/ca/sd) muessen mit rein: football-data schreibt
    # "RC Deportivo La Coruña", unser Katalog "Deportivo La Coruña".
    s = re.sub(r'\b(fc|cf|ac|as|ss|us|sc|sd|rc|rcd|ud|cd|ca|afc|ssc|calcio|club|de|deportivo'
               r'|futbol|football)\b', ' ', s)
    return ' '.join(s.split())


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
    key = api_key()
    print('Quelle: football-data.org' if key else
          'Quelle: Wikipedia (kein football-data-Key gefunden — Fallback)')

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
    for league, (code, page, expected) in LEAGUES.items():
        source = 'football-data'
        wanted = clubs_from_api(code, key) if key else []
        if len(wanted) != expected:
            wanted = clubs_from_wikipedia(page)
            source = 'Wikipedia'
        if len(wanted) != expected:
            print(f'\n### {league}: Teilnehmerliste NICHT VERWERTBAR — {len(wanted)} statt '
                  f'{expected} Vereinen gelesen. Kein Diff (er waere Rauschen), bleibt MANUELL.')
            exit_code = 1
            continue

        seen, wrong, missing = set(), [], []
        for short, full in wanted:
            slug = (strict_lookup.get(strict(short)) or strict_lookup.get(strict(full))
                    or lookup.get(norm(short)) or lookup.get(norm(full)))
            if slug is None:
                missing.append(short)
                continue
            seen.add(slug)
            if db[slug]['league'] != league:
                wrong.append((short, db[slug]['league'], slug))
        extra = [(s, t['name']) for s, t in db.items() if t['league'] == league and s not in seen]

        print(f'\n### {league} ({source}) — Kader {len(wanted)}, DB fuehrt '
              f'{sum(1 for t in db.values() if t["league"] == league)}')
        for name, have, slug in wrong:
            print(f'   WECHSEL   {name:32} DB: {have:22} [{slug}]')
        for name in missing:
            print(f'   FEHLT     {name:32} (nicht in open-jersey-db)')
        for slug, name in extra:
            print(f'   ZUVIEL    {name:32} steht in {league}, aber nicht im Kader [{slug}]')
        if wrong or missing or extra:
            exit_code = 1
        else:
            print('   deckungsgleich')

    return exit_code


if __name__ == '__main__':
    sys.exit(main())
