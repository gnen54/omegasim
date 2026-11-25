"""Boxenfelder (gelb gestrichelt) und Einfahrtspfeil aus der DXF in eine Strecken-JSON uebernehmen.
python3 boxfelder.py Toernerschleife-V2c.dxf ../../img/strecken/indeq-bruecke.json

Boxenfelder: alle LINE-Elemente mit Farbe 2 (gelb) -> d['boxFelder'] = [[x0, y0, x1, y1], ...]
Pfeil: geschlossene LWPOLYLINE mit 7 Ecken -> d['boxPfeil'] = Dreiecke [x0, y0, x1, y1, x2, y2, ...]
Umrechnung mm -> Karte wie boxgasse.py (K, Spiegelung von y, Versatz aus d['_versatz'])."""
import sys, json
import numpy as np

K = 0.093023
dxf, js = sys.argv[1], sys.argv[2]


def elemente(fn):
    L = [l.strip() for l in open(fn, errors='replace').read().splitlines()]
    pairs = [(L[i], L[i + 1]) for i in range(0, len(L) - 1, 2)]
    i = [k for k, (c, v) in enumerate(pairs) if c == '2' and v == 'ENTITIES'][0]
    ents, cur = [], None
    for c, v in pairs[i + 1:]:
        if c == '0':
            if cur: ents.append(cur)
            if v == 'ENDSEC': break
            cur = {'t': v, 'g': []}
        elif cur is not None: cur['g'].append((c, v))
    return ents


def dreiecke(P):
    """Ear Clipping fuer ein einfaches Polygon (Liste von Punkten)."""
    P = [tuple(p) for p in P]
    if sum(P[i][0] * P[(i + 1) % len(P)][1] - P[(i + 1) % len(P)][0] * P[i][1] for i in range(len(P))) < 0: P = P[::-1]
    kreuz = lambda a, b, c: (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    def drin(p, a, b, c): return kreuz(a, b, p) >= 0 and kreuz(b, c, p) >= 0 and kreuz(c, a, p) >= 0
    idx, out = list(range(len(P))), []
    while len(idx) > 3:
        for k in range(len(idx)):
            a, b, c = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            if kreuz(P[a], P[b], P[c]) <= 0: continue
            if any(drin(P[j], P[a], P[b], P[c]) for j in idx if j not in (a, b, c)): continue
            out.append((P[a], P[b], P[c])); idx.pop(k); break
        else: raise SystemExit('Polygon nicht zerlegbar')
    out.append(tuple(P[j] for j in idx))
    return out


d = json.load(open(js, encoding='utf-8'))
v = d['_versatz']
ed = lambda x, y: [round(x * K - v[0], 3), round(-y * K - v[1], 3)]
felder, pfeil = [], None
for e in elemente(dxf):
    g = e['g']; f = lambda code: [float(x) for c, x in g if c == code]
    farbe = [int(x) for c, x in g if c == '62']
    if e['t'] == 'LINE' and farbe == [2]:
        felder.append(ed(f('10')[0], f('20')[0]) + ed(f('11')[0], f('21')[0]))
    elif e['t'] == 'LWPOLYLINE' and len(f('10')) == 7:
        pfeil = [ed(x, y) for x, y in zip(f('10'), f('20'))]
d['boxFelder'] = felder
if pfeil:
    d['boxPfeil'] = [c for t in dreiecke(pfeil) for p in t for c in p]
json.dump(d, open(js, 'w', encoding='utf-8'), separators=(',', ':'))
print(len(felder), 'Boxenfeld-Linien;', len(d.get('boxPfeil', [])) // 6, 'Pfeil-Dreiecke')
