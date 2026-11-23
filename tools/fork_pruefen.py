#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fork gnen54: Pruefung, ob Luukes Code und die Fork-Datei noch zusammenpassen.

    python3 tools/fork_pruefen.py            pruefen (Exit-Code 1 bei Abweichung)
    python3 tools/fork_pruefen.py --merken   aktuelle Fingerabdruecke speichern (nur nach Durchsicht!)

1. Fingerabdruecke: src/98z-fork-gnen54.js ersetzt einige Funktionen aus src/60d-virtuell.js ganz
   (Liste VF_FORK_ERSETZT). Aendert Luuke eine davon, wuerde seine Aenderung still verdeckt. Darum wird
   von jeder dieser Funktionen in 60d-virtuell.js ein Fingerabdruck (SHA-256) gespeichert
   (tools/fork/fingerabdruecke.json). Weicht er ab: Luukes neue Fassung ansehen, das Sinnvolle in die
   Fork-Fassung uebernehmen, dann --merken.
2. Einhaengepunkte: jede Funktion vfForkXxx aus der Fork-Datei muss in 60d-virtuell.js aufgerufen werden
   (sonst ist der Einhaengepunkt bei einem Update verloren gegangen).
"""
import hashlib
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORK = os.path.join(REPO, 'src', '98z-fork-gnen54.js')
LUUKE = os.path.join(REPO, 'src', '60d-virtuell.js')
ABDRUCK = os.path.join(REPO, 'tools', 'fork', 'fingerabdruecke.json')


def funktion(src, name):
    m = re.search(r'^  function\*? ' + re.escape(name) + r'\(', src, re.M)
    if not m:
        return None
    return src[m.start():src.index('\n  }\n', m.start()) + 5]


def abdruck(text):
    norm = '\n'.join(z.rstrip() for z in text.split('\n'))
    return hashlib.sha256(norm.encode('utf-8')).hexdigest()[:16]


def main():
    fork = open(FORK, encoding='utf-8').read()
    luuke = open(LUUKE, encoding='utf-8').read()
    namen = json.loads(re.search(r'VF_FORK_ERSETZT = (\[[^\]]*\])', fork).group(1).replace("'", '"'))
    jetzt = {}
    fehler = []
    for n in namen:
        f = funktion(luuke, n)
        if f is None:
            fehler.append('%s: gibt es in 60d-virtuell.js nicht mehr (Luuke hat sie umbenannt oder entfernt)' % n)
            continue
        if funktion(fork, n) is None:
            fehler.append('%s: fehlt in der Fork-Datei' % n)
        jetzt[n] = abdruck(f)
    if '--merken' in sys.argv:
        os.makedirs(os.path.dirname(ABDRUCK), exist_ok=True)
        with open(ABDRUCK, 'w', encoding='utf-8') as d:
            json.dump(jetzt, d, indent=1, sort_keys=True)
            d.write('\n')
        print('Fingerabdruecke gespeichert:', ', '.join(sorted(jetzt)))
        return 0 if not fehler else 1
    alt = json.load(open(ABDRUCK, encoding='utf-8')) if os.path.exists(ABDRUCK) else {}
    for n, h in sorted(jetzt.items()):
        if alt.get(n) != h:
            fehler.append('%s: Luuke hat die Funktion geaendert - Fork-Fassung pruefen, dann --merken' % n)
    for h in sorted(set(re.findall(r'^  function (vfFork\w+)\(', fork, re.M))):
        if h + '(' not in luuke:
            fehler.append('Einhaengepunkt %s wird in 60d-virtuell.js nicht mehr aufgerufen' % h)
    if fehler:
        print('FORK-PRUEFUNG: %d Punkt(e)' % len(fehler))
        for f in fehler:
            print('  -', f)
        return 1
    print('Fork-Pruefung ok: %d ersetzte Funktionen unveraendert, alle Einhaengepunkte vorhanden' % len(jetzt))
    return 0


if __name__ == '__main__':
    sys.exit(main())
