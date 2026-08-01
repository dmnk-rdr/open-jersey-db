#!/usr/bin/env python3
"""Diff: OpenLigaDB-Kader 2026/27 (bl1/bl2/bl3) gegen die Liga-Zuordnung in open-jersey-db.

Read-only. Gibt drei Klassen aus:
  WECHSEL  — Verein liegt in open-jersey-db in einer anderen der drei getrackten Ligen
  NEU      — Verein in der API, aber gar nicht in open-jersey-db
  RAUS     — Verein in einer der drei Ligen laut open-jersey-db, aber in keiner API-Liste
             (= in eine nicht getrackte Liga abgestiegen → MANUELL recherchieren)
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / 'data' / 'teams' / 'football'
TRACKED = {'bl1': 'bundesliga', 'bl2': '2-bundesliga', 'bl3': '3-liga'}
YEAR = 2026


def norm(s):
    s = s.lower().strip()
    for a, b in (('ä', 'ae'), ('ö', 'oe'), ('ü', 'ue'), ('ß', 'ss')):
        s = s.replace(a, b)
    s = re.sub(r'[^a-z0-9]+', ' ', s)
    return ' '.join(s.split())


def load_db():
    """slug -> {name, league, aliases[]} für ALLE Fußball-Ligen."""
    teams = {}
    for f in DB.rglob('*.yaml'):
        txt = f.read_text(encoding='utf-8')
        name = re.search(r'^name:\s*(.+)$', txt, re.M)
        league = re.search(r'^league:\s*(.+)$', txt, re.M)
        aliases = re.findall(r'^-\s*(.+)$', txt.split('aliases:')[1].split('\n\n')[0], re.M) \
            if 'aliases:' in txt else []
        teams[f.stem] = {
            'name': name.group(1).strip() if name else f.stem,
            'league': league.group(1).strip() if league else f.parent.name,
            'aliases': [a.strip() for a in aliases if not a.strip().startswith('{')],
            'path': f,
        }
    return teams


def api(shortcut):
    url = f'https://api.openligadb.de/getavailableteams/{shortcut}/{YEAR}'
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def main():
    db = load_db()
    lookup = {}
    for slug, t in db.items():
        for key in [norm(t['name']), norm(slug)] + [norm(a) for a in t['aliases']]:
            lookup.setdefault(key, slug)

    seen, changes, new = set(), [], []
    for shortcut, league in TRACKED.items():
        for team in api(shortcut):
            cands = [norm(team.get('teamName', '')), norm(team.get('shortName', ''))]
            slug = next((lookup[c] for c in cands if c in lookup), None)
            if slug is None:
                new.append((team.get('teamName'), league))
                continue
            seen.add(slug)
            if db[slug]['league'] != league:
                changes.append((slug, db[slug]['name'], db[slug]['league'], league))

    gone = [(s, t['name'], t['league']) for s, t in db.items()
            if t['league'] in TRACKED.values() and s not in seen]

    print(f'=== WECHSEL ({len(changes)}) ===')
    for slug, name, old, newl in sorted(changes, key=lambda x: x[3]):
        print(f'  {name:34} {old:16} -> {newl}   [{slug}]')
    print(f'\n=== NEU, nicht in open-jersey-db ({len(new)}) ===')
    for name, league in sorted(new, key=lambda x: x[1]):
        print(f'  {name:34} -> {league}')
    print(f'\n=== RAUS aus den 3 Ligen ({len(gone)}) — Zielliga MANUELL ===')
    for slug, name, old in sorted(gone, key=lambda x: x[2]):
        print(f'  {name:34} war {old:16} [{slug}]')


if __name__ == '__main__':
    sys.exit(main())
