#!/usr/bin/env python3
"""Vereinfacht ein Automodell (img/autos/<name>/auto.bin + auto.json) auf eine Zieldreieckszahl.

21.11.2026 (GEMELDET Luke/Gnen54: "im Performance Modus mit Manta extrem schlecht, 5-10 fps", "es ruckelt,
im Porsche etwas besser"): Manta 1,46 Mio., GT3 2,0 Mio., Bulli 1,67 Mio. Dreiecke - Kaefer 0,14 Mio.
Mit drei NPCs und dem Innenspiegel kommen schnell 10 Mio. Dreiecke je Bild zusammen.

Verfahren: Eckpunkt-Clusterung je Teil auf einem Wuerfelraster. Damit harte Kanten und Textur-
naehte erhalten bleiben, gehoeren zur Zelle auch die grobe Normalenrichtung und die (grob gerundete)
Texturkoordinate. Je Zelle: mittlere Position, gemittelte Normale, UV des ersten Punkts. Entartete und
doppelte Dreiecke fallen weg. Die Zellgroesse wird gesucht, bis die Zieldreieckszahl erreicht ist.
Eckpunkt: 8 float32 (x y z nx ny nz u v), Indizes uint16 je Teil relativ zu ecke0.

Aufruf: python3 tools/modell_lod.py <ordner> <ziel_dreiecke> [--sicherung <ordner>] [--behalten <Regex Teilname>]
"""
import json, os, re, shutil, sys
import numpy as np


def lade(d):
    meta = json.load(open(os.path.join(d, 'auto.json'), encoding='utf-8'))
    raw = open(os.path.join(d, 'auto.bin'), 'rb').read()
    E = np.frombuffer(raw, dtype=np.float32, count=meta['ecken'] * 8).reshape(-1, 8)
    I = np.frombuffer(raw, dtype=np.uint16, count=meta['indizes'], offset=meta['indexAb'])
    return meta, E, I


def teil_vereinfachen(E, I, zelle):
    P, N, UV = E[:, :3], E[:, 3:6], E[:, 6:8]
    nb = np.round(N * 1.4).astype(np.int32)                 # grobe Richtung (harte Kanten bleiben)
    uvq = np.round(UV * 48).astype(np.int32)                 # Texturnaehte bleiben
    gq = np.floor(P / zelle).astype(np.int64)
    key = np.concatenate([gq, nb, uvq], axis=1)
    _, inv, first = None, None, None
    uniq, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inv = inv.reshape(-1)
    m = len(uniq)
    cnt = np.bincount(inv, minlength=m).astype(np.float32)
    Pm = np.stack([np.bincount(inv, P[:, k], m) for k in range(3)], 1) / cnt[:, None]
    # Je Zelle den ORIGINALpunkt nehmen, der dem Mittel am naechsten liegt: so bleiben die Punkte auf der
    # echten Flaeche. Mit dem Mittel rutschten sie in Woelbungen nach innen, und uebereinander liegende
    # Lackschichten (Manta: Gelb unter Grau/Weiss) stachen durch.
    d2 = np.sum((P - Pm[inv]) ** 2, axis=1)
    o = np.lexsort((d2, inv))
    erst = np.ones(len(o), bool); erst[1:] = inv[o][1:] != inv[o][:-1]
    rep = np.empty(m, np.int64); rep[inv[o][erst]] = o[erst]
    Pn = P[rep]
    Nn = np.stack([np.bincount(inv, N[:, k], m) for k in range(3)], 1)
    Nn /= np.maximum(np.linalg.norm(Nn, axis=1, keepdims=True), 1e-9)
    UVn = UV[rep]
    T = inv[I.reshape(-1, 3).astype(np.int64)]
    ok = (T[:, 0] != T[:, 1]) & (T[:, 1] != T[:, 2]) & (T[:, 0] != T[:, 2])
    T = T[ok]
    s = np.sort(T, axis=1)
    _, iu = np.unique(s, axis=0, return_index=True)
    T = T[np.sort(iu)]
    # nur benutzte Ecken behalten
    used = np.unique(T)
    remap = -np.ones(m, np.int64); remap[used] = np.arange(len(used))
    En = np.concatenate([Pn[used], Nn[used], UVn[used]], 1).astype(np.float32)
    return En, remap[T].astype(np.uint16).reshape(-1)


def vereinfachen(meta, E, I, zelle, behalten=None):
    teile, Es, Is, e0, i0 = [], [], [], 0, 0
    for t in meta['teile']:
        Et = E[t['ecke0']:t['ecke0'] + t['ecken']]
        It = I[t['index0']:t['index0'] + t['indizes']]
        # kleine Teile (Lichter, Kleinteile) bleiben wie sie sind
        # kleine Teile und aufgelegte Lackschichten (sonst stechen die Schichten durcheinander)
        if t['indizes'] < 3000 or (behalten and re.search(behalten, t['name'])):
            En, In = Et.copy(), It.copy()
        else:
            En, In = teil_vereinfachen(Et, It, zelle)
            if len(In) < 3:
                En, In = Et.copy(), It.copy()
        nt = dict(t); nt.update(ecke0=e0, ecken=len(En), index0=i0, indizes=len(In))
        teile.append(nt); Es.append(En); Is.append(In); e0 += len(En); i0 += len(In)
    return teile, np.concatenate(Es), np.concatenate(Is)


def main():
    d, ziel = sys.argv[1], int(sys.argv[2])
    sich = sys.argv[sys.argv.index('--sicherung') + 1] if '--sicherung' in sys.argv else None
    beh = sys.argv[sys.argv.index('--behalten') + 1] if '--behalten' in sys.argv else None
    meta, E, I = lade(d)
    vorher = meta['indizes'] // 3
    lo, hi = 0.001, 0.08                                     # Zellgroesse in m (Modell in Originalgroesse)
    best = None
    for _ in range(14):
        z = (lo * hi) ** 0.5
        teile, En, In = vereinfachen(meta, E, I, z, beh)
        n = len(In) // 3
        if n > ziel: lo = z
        else: hi = z; best = (z, teile, En, In)
        if best and abs(n - ziel) < ziel * 0.06: break
    if not best:
        best = (hi,) + vereinfachen(meta, E, I, hi, beh)
    z, teile, En, In = best
    if sich:
        os.makedirs(sich, exist_ok=True)
        for f in ('auto.bin', 'auto.json'):
            if not os.path.exists(os.path.join(sich, f)):
                shutil.copy2(os.path.join(d, f), os.path.join(sich, f))
    pad = (-En.nbytes) % 4
    meta.update(teile=teile, ecken=len(En), indizes=len(In), indexAb=En.nbytes + pad)
    meta['lod'] = 'vereinfacht von %d auf %d Dreiecke (Zelle %.1f mm, tools/modell_lod.py)' % (vorher, len(In) // 3, z * 1000)
    with open(os.path.join(d, 'auto.bin'), 'wb') as f:
        f.write(En.tobytes()); f.write(b'\0' * pad); f.write(In.tobytes())
    json.dump(meta, open(os.path.join(d, 'auto.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(d, meta['lod'], 'Datei %.1f MB' % (os.path.getsize(os.path.join(d, 'auto.bin')) / 1e6))


if __name__ == '__main__':
    main()
