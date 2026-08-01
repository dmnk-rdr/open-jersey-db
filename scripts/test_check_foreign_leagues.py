#!/usr/bin/env python3
"""Guards fuer die Drosselung und die Fehlerbehandlung in check_foreign_leagues.py.

Laeuft OHNE Netz: `_get` wird durch Attrappen ersetzt. Damit bleibt das echte Free-Tier-
Kontingent (10 Anfragen/Minute) unangetastet und der Test dauert Sekunden statt Minuten.

Aufruf:  python3 scripts/test_check_foreign_leagues.py
"""
import importlib.util
import io
import json
import sys
import time
import urllib.error
from pathlib import Path


def load():
    spec = importlib.util.spec_from_file_location(
        'cfl', Path(__file__).resolve().parent / 'check_foreign_leagues.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeResponse(io.StringIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def http_error(code, headers=None):
    return urllib.error.HTTPError('https://api.example/x', code, 'nope', headers or {}, None)


def test_throttle_waits_once_the_window_is_full():
    """Nach RATE_LIMIT_CALLS Anfragen im Fenster MUSS gewartet werden.

    Fenster fuer den Test gestaucht (3 Anfragen / 2s); die Logik ist dieselbe wie bei 10/60s.
    """
    cfl = load()
    cfl.RATE_LIMIT_CALLS, cfl.RATE_LIMIT_WINDOW, cfl.MAX_SLEEP = 3, 2.0, 5.0
    start = time.monotonic()
    for _ in range(7):
        cfl._throttle()
    elapsed = time.monotonic() - start
    assert elapsed >= 4.0, f'Drosselung griff nicht (nur {elapsed:.2f}s fuer 7 Anfragen)'


def test_rate_limit_is_retried_once_and_then_succeeds():
    """429 ist voruebergehend: einmal warten (der Reset-Header sagt wie lange), dann erneut."""
    cfl = load()
    cfl.MAX_SLEEP, cfl.RATE_LIMIT_WINDOW = 1.0, 0.01
    calls = {'n': 0}

    def get(url, headers):
        calls['n'] += 1
        if calls['n'] == 1:
            raise http_error(429, {'X-RequestCounter-Reset': '1'})
        return FakeResponse(json.dumps({'teams': [{'shortName': 'Arsenal', 'name': 'Arsenal FC'}]}))

    cfl._get = get
    assert cfl.clubs_from_api('PL', 'dummy') == [('Arsenal', 'Arsenal FC')]
    assert calls['n'] == 2, f'erwartet 1 Fehlschlag + 1 Retry, waren {calls["n"]}'


def test_persistent_rate_limit_gives_up_instead_of_looping():
    """Genau EIN Retry — sonst haengt ein Rollover-Lauf an einer schmollenden API fest."""
    cfl = load()
    cfl.MAX_SLEEP, cfl.RATE_LIMIT_WINDOW = 1.0, 0.01
    calls = {'n': 0}

    def get(url, headers):
        calls['n'] += 1
        raise http_error(429, {'X-RequestCounter-Reset': '1'})

    cfl._get = get
    assert cfl.clubs_from_api('PL', 'dummy') == []
    assert calls['n'] == 2, f'darf genau 2x versuchen, waren {calls["n"]}'


def test_forbidden_is_not_retried():
    """403 heisst "nicht im Free-Tier" (z. B. Segunda Division) — ein Retry waere sinnlos."""
    cfl = load()
    calls = {'n': 0}

    def get(url, headers):
        calls['n'] += 1
        raise http_error(403)

    cfl._get = get
    assert cfl.clubs_from_api('SD', 'dummy') == []
    assert calls['n'] == 1, f'403 darf NICHT wiederholt werden, waren {calls["n"]}'


def main():
    failed = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith('test_'):
            continue
        try:
            fn()
            print(f'  ok    {name}')
        except AssertionError as exc:
            print(f'  FAIL  {name}: {exc}')
            failed += 1
    print('alle Guards gruen' if not failed else f'{failed} Guard(s) rot')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
