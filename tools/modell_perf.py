#!/usr/bin/env python3
"""Leichte Fassung eines Automodells fuer den Grafikmodus Performance -> auto_perf.json + auto_perf.bin.

22.11.2026 (GEMELDET Gnen54, Android-Tablet, App aus dem Fork): "furchtbar zu fahren" mit Spider, GT3,
Bulli und Manta - ruckelig, Bild unkonstant; nur der Kaefer laeuft im Performance-Modus. GT3 2,0 Mio.,
Bulli 1,7 Mio., Manta 1,5 Mio. Dreiecke; dazu die Raeder (Reifen vorn mit Profil 54 000 Dreiecke), die
je Achse zweimal gezeichnet werden.

Quality laedt weiter auto.bin in voller Aufloesung (auto.json/auto.bin bleiben unberuehrt). Performance
laedt die Datei, die auto.json unter "perf" nennt.

Verfahren (anders als tools/modell_lod.py, dessen Eckpunkt-Clusterung am Manta-Heck unschoen aussah):
- Alle grossen Karosserieteile werden zusammengelegt, nach Position verschweisst und GEMEINSAM mit
  Quadrik-Kantenkollaps (tools/qem/qem.c) vereinfacht, das Teil als Material je Dreieck. Offene Kanten und
  Materialgrenzen (GT3 weiss/rot) werden nur entlang ihrer Linie verkuerzt: keine Risse, glatte Farbgrenzen.
  Der Fehler verteilt sich gleichmaessig ueber das ganze Auto. Raeder je Teil fuer sich.
- Normalen neu mit 35-Grad-Knick (wie beim Bau der Modelle), Texturkoordinate vom naechsten Originalpunkt.
- Danach wieder in Stuecke <= 65 535 Ecken (Indizes uint16).
- Kleine Teile (< 3000 Dreiecke) und Scheinwerfer mit eigenem Glas (Glas liegt 0,06 mm davor) bleiben.

Aufruf: python3 tools/modell_perf.py <ordner> <ziel_dreiecke_karosserie> <ziel_je_radteil>
Braucht tools/qem/qem.so (gcc -O2 -shared -fPIC -o tools/qem/qem.so tools/qem/qem.c -lm).
"""
import ctypes, json, os, re, sys
import numpy as np
from scipy.spatial import cKDTree

HIER = os.path.dirname(os.path.abspath(__file__))
_lib = None


def qem_lib():
    global _lib
    if _lib is None:
        so = os.environ.get('QEM_SO') or os.path.join(HIER, 'qem', 'qem.so')
        _lib = ctypes.CDLL(so)
        _lib.qem.restype = ctypes.c_int
    return _lib


def qem(P, T, M, ziel, aggr=7.0, wrand=None):
    if wrand is None: wrand = float(os.environ.get('QEM_WRAND', '100'))
    P = np.ascontiguousarray(P, np.float64); T = np.ascontiguousarray(T, np.int32); M = np.ascontiguousarray(M, np.int32)
    po = np.zeros_like(P); to = np.zeros_like(T); oo = np.zeros(len(T), np.int32); nv = ctypes.c_int(0)
    d = ctypes.POINTER(ctypes.c_double); i = ctypes.POINTER(ctypes.c_int)
    nt = qem_lib().qem(len(P), P.ctypes.data_as(d), len(T), T.ctypes.data_as(i), M.ctypes.data_as(i), int(ziel),
                       ctypes.c_double(aggr), ctypes.c_double(wrand), po.ctypes.data_as(d), to.ctypes.data_as(i),
                       oo.ctypes.data_as(i), ctypes.byref(nv))
    return po[:nv.value], to[:nt], oo[:nt]


def lade(d):
    meta = json.load(open(os.path.join(d, 'auto.json'), encoding='utf-8'))
    raw = open(os.path.join(d, 'auto.bin'), 'rb').read()
    E = np.frombuffer(raw, dtype=np.float32, count=meta['ecken'] * 8).reshape(-1, 8)
    I = np.frombuffer(raw, dtype=np.uint16, count=meta['indizes'], offset=meta['indexAb'])
    return meta, E, I


def eckennormalen(P, T, knick_grad=35.0):
    """Normale je Dreiecksecke: Mittel der Nachbarflaechen an derselben Ecke, die weniger als knick_grad
    von der eigenen Flaeche abweichen (flaechengewichtet)."""
    Fn = np.cross(P[T[:, 1]] - P[T[:, 0]], P[T[:, 2]] - P[T[:, 0]])
    Fu = Fn / np.maximum(np.linalg.norm(Fn, axis=1, keepdims=True), 1e-20)
    nf = len(T)
    ecke_v = T.reshape(-1); ecke_f = np.repeat(np.arange(nf), 3)
    o = np.argsort(ecke_v, kind='stable'); sv = ecke_v[o]; sf = ecke_f[o]
    start = np.searchsorted(sv, np.arange(len(P))); anz = np.searchsorted(sv, np.arange(len(P)), 'right') - start
    # Paare (Ecke c, Nachbarflaeche g) ueber alle Flaechen an derselben Ecke
    ca = np.repeat(np.arange(3 * nf), anz[ecke_v])
    off = np.arange(len(ca)) - np.repeat(np.cumsum(anz[ecke_v]) - anz[ecke_v], anz[ecke_v])
    g = sf[start[ecke_v[ca]] + off]
    ok = np.einsum('ij,ij->i', Fu[ecke_f[ca]], Fu[g]) > np.cos(np.radians(knick_grad))
    N = np.zeros((3 * nf, 3))
    np.add.at(N, ca[ok], Fn[g[ok]])
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-20)
    return N.reshape(nf, 3, 3)


def offene_kanten(T):
    e = np.r_[T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]]
    f = np.tile(np.arange(len(T)), 3); j = np.repeat([0, 1, 2], len(T))
    s = np.sort(e, axis=1)
    _, inv, c = np.unique(s, axis=0, return_inverse=True, return_counts=True)
    m = c[inv.reshape(-1)] == 1
    return e[m], f[m], j[m]

def zip_t(P, T, M, eps=2e-5):
    """T-Stellen schliessen: liegt eine Randecke auf einer fremden Randkante (Abstand < eps), wird die Kante
    und ihr Dreieck dort geteilt. GT3: Weiss und Rot waren an der Farbgrenze unabhaengig unterteilt, ihre
    Raender teilten keine Kanten (105 000 offene Kanten, danach 400). Ohne das bleiben die Raender beim
    Vereinfachen dicht und der Rest der Karosserie faellt zu grossen Flaechen zusammen."""
    for runde in range(3):
        E_, F_, J_ = offene_kanten(T)
        if not len(E_): break
        A = P[E_[:, 0]]; B = P[E_[:, 1]]
        rv = np.unique(E_)
        mid = (A + B) / 2; half = np.linalg.norm(B - A, axis=1) / 2
        tree = cKDTree(mid); R = half.max() + eps
        splits = {}
        kand = tree.query_ball_point(P[rv], r=R)
        for v, lst in zip(rv, kand):
            if not lst: continue
            lst = np.array(lst)
            lst = lst[(E_[lst, 0] != v) & (E_[lst, 1] != v)]
            if not len(lst): continue
            a = A[lst]; d = B[lst] - a; l2 = np.einsum('ij,ij->i', d, d)
            t = np.einsum('ij,ij->i', P[v] - a, d) / np.maximum(l2, 1e-30)
            q = a + d * t[:, None]; dist = np.linalg.norm(P[v] - q, axis=1)
            ok = (t > 1e-4) & (t < 1 - 1e-4) & (dist < eps)
            for k in lst[ok]:
                tt = t[np.where(lst == k)[0][0]]
                splits.setdefault(int(k), []).append((tt, int(v)))
        if not splits: break
        neu = []; neu_m = []; weg = np.zeros(len(T), bool)
        for k, pts in splits.items():
            f, j = F_[k], J_[k]
            a, b, c = T[f, j], T[f, (j + 1) % 3], T[f, (j + 2) % 3]
            if weg[f]:
                continue   # Dreieck schon an anderer Kante geteilt: naechste Runde
            weg[f] = True
            kette = [a] + [v for _, v in sorted(pts)] + [b]
            for x, y in zip(kette[:-1], kette[1:]): neu.append((x, y, c)); neu_m.append(M[f])
        T = np.vstack([T[~weg], np.array(neu, dtype=T.dtype)]); M = np.r_[M[~weg], np.array(neu_m, dtype=M.dtype)]
    return T, M

def einheit_vereinfachen(Eg, Ig, Mg, ziel):
    """Eine Einheit (mehrere Gruppen, Material Mg je Dreieck) gemeinsam vereinfachen. Gibt je Material
    (Ecken n x 8, Dreiecke m x 3) zurueck. Gemeinsam heisst: der Fehler verteilt sich gleichmaessig ueber
    das ganze Auto, Kleinteile behalten so viel Aufloesung wie sie fuer ihre Form brauchen."""
    P = Eg[:, :3].astype(np.float64)
    key = np.round(P * 1e5).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inv = inv.reshape(-1)
    Pw = P[first]; Tw = inv[Ig]
    ok = (Tw[:, 0] != Tw[:, 1]) & (Tw[:, 1] != Tw[:, 2]) & (Tw[:, 0] != Tw[:, 2])
    Tw = Tw[ok]; Mw = Mg[ok]
    Tw, Mw = zip_t(Pw, Tw, Mw)
    Pn, Tn, On = qem(Pw, Tw, Mw, ziel)
    Mn = Mw[On]
    aus = {}
    for m in np.unique(Mn):
        sel = Mn == m
        T = Tn[sel]; u, Tl = np.unique(T, return_inverse=True); Tl = Tl.reshape(-1, 3); Pl = Pn[u]
        N = eckennormalen(Pl, Tl)
        # Texturkoordinate: naechster Originalpunkt desselben Materials
        om = np.unique(Ig[Mg == m]); _, nn = cKDTree(P[om]).query(Pl); UV = Eg[om[nn], 6:8]
        ev = Tl.reshape(-1); en = N.reshape(-1, 3)
        k2 = np.c_[ev, np.round(en * 2000).astype(np.int64)]
        _, f2, inv2 = np.unique(k2, axis=0, return_index=True, return_inverse=True)
        En = np.concatenate([Pl[ev[f2]], en[f2], UV[ev[f2]]], 1).astype(np.float32)
        aus[int(m)] = (En, inv2.reshape(-1, 3))
    return aus


def stuecke(En, Tn, maxe=65535):
    """In Stuecke mit hoechstens maxe Ecken teilen (Dreiecke der Reihe nach)."""
    if len(En) <= maxe:
        return [(En, Tn.astype(np.uint16).reshape(-1))]
    aus, i = [], 0
    while i < len(Tn):
        # so viele Dreiecke, dass hoechstens maxe Ecken gebraucht werden
        lo, hi = 1, len(Tn) - i
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if len(np.unique(Tn[i:i + mid])) <= maxe: lo = mid
            else: hi = mid - 1
        T = Tn[i:i + lo]; u, inv = np.unique(T, return_inverse=True)
        aus.append((En[u], inv.astype(np.uint16).reshape(-1))); i += lo
    return aus


def main():
    d, ziel_k, ziel_r = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    meta, E, I = lade(d)
    hat_glas = any(t.get('rolle') == 'scheinwerferglas' for t in meta['teile'])
    gruppen, reihe = {}, []
    for t in meta['teile']:
        k = (re.sub(r'\s+\d+$', '', t['name']), t.get('rolle'), t.get('gruppe'), t.get('tex'), t.get('achse'))
        if k not in gruppen: gruppen[k] = []; reihe.append(k)
        gruppen[k].append(t)
    def n_dr(k): return sum(t['indizes'] for t in gruppen[k]) // 3
    def bleibt(k): return n_dr(k) < 3000 or (hat_glas and k[1] in ('scheinwerfer', 'scheinwerferglas'))
    def daten(k):
        tl = gruppen[k]
        Eg = np.concatenate([E[t['ecke0']:t['ecke0'] + t['ecken']] for t in tl])
        offs = np.cumsum([0] + [t['ecken'] for t in tl])[:-1]
        Ig = np.concatenate([I[t['index0']:t['index0'] + t['indizes']].astype(np.int64) + o for t, o in zip(tl, offs)]).reshape(-1, 3)
        return Eg, Ig
    ergebnis = {}
    # Karosserie-Einheit: alle grossen Teile der Gruppe "auto" gemeinsam
    # Scheiben und Leuchten fuer sich (Anteil wie die Karosserie): gemeinsam mit ihr wuerden die fast ebenen
    # Scheiben bis auf wenige Dreiecke zusammenfallen, weil die Karosserie mit ihren vielen festen
    # Randecken den Fehler hochtreibt.
    eigen = [k for k in reihe if k[2] != 'rad' and not bleibt(k) and k[1] in ('glas', 'ruecklicht', 'scheinwerfer', 'scheinwerferglas')]
    karo = [k for k in reihe if k[2] != 'rad' and not bleibt(k) and k not in eigen]
    fest = sum(n_dr(k) for k in reihe if k[2] != 'rad' and bleibt(k))
    if karo:
        Es_, Is_, Ms_, off = [], [], [], 0
        for m, k in enumerate(karo):
            Eg, Ig = daten(k); Es_.append(Eg); Is_.append(Ig + off); Ms_.append(np.full(len(Ig), m)); off += len(Eg)
        ziel_e = ziel_k - fest - sum(max(400, int(n_dr(k) * max(0.08, (ziel_k - fest) / max(1, sum(n_dr(kk) for kk in karo + eigen))))) for k in eigen)
        aus = einheit_vereinfachen(np.concatenate(Es_), np.concatenate(Is_), np.concatenate(Ms_), max(1000, ziel_e))
        for m, k in enumerate(karo):
            if m in aus: ergebnis[k] = aus[m]
    anteil = max(0.08, (ziel_k - fest) / max(1, sum(n_dr(k) for k in karo + eigen)))
    for k in eigen:
        Eg, Ig = daten(k)
        ergebnis[k] = einheit_vereinfachen(Eg, Ig, np.zeros(len(Ig), np.int64), max(400, int(n_dr(k) * anteil)))[0]
    for k in reihe:
        if k[2] == 'rad' and not bleibt(k) and n_dr(k) > ziel_r:
            Eg, Ig = daten(k)
            ergebnis[k] = einheit_vereinfachen(Eg, Ig, np.zeros(len(Ig), np.int64), ziel_r)[0]
    teile, Es, Is, e0, i0 = [], [], [], 0, 0
    for k in reihe:
        tl = gruppen[k]
        if k in ergebnis:
            stk = stuecke(*ergebnis[k])
        elif k in karo:
            print('  %-28s entfaellt (ganz weg vereinfacht)' % k[0]); continue
        else:
            stk = [(E[t['ecke0']:t['ecke0'] + t['ecken']].copy(), I[t['index0']:t['index0'] + t['indizes']].copy()) for t in tl]
        for j, (Es_, Is_) in enumerate(stk):
            nt = {kk: v for kk, v in tl[0].items() if kk not in ('ecke0', 'ecken', 'index0', 'indizes')}
            if k in ergebnis: nt['name'] = k[0] + (' %d' % (j + 1) if len(stk) > 1 else '')
            elif len(tl) > 1: nt['name'] = tl[j]['name']
            nt.update(ecke0=e0, ecken=len(Es_), index0=i0, indizes=len(Is_))
            teile.append(nt); Es.append(Es_); Is.append(Is_); e0 += len(Es_); i0 += len(Is_)
        print('  %-28s %8d -> %8d' % (k[0][:28], n_dr(k), sum(len(x[1]) for x in stk) // 3))
    En = np.concatenate(Es); In = np.concatenate(Is)
    pad = (-En.nbytes) % 4
    # Nur die Geometrie: alles andere (Physik, Lichter, Kamera ...) liest die App weiter aus auto.json,
    # damit eine spaetere Aenderung dort nicht in einer veralteten Kopie haengen bleibt.
    vorher = meta['indizes'] // 3
    pm = {'lod': 'Performance-Fassung: %d statt %d Dreiecke (tools/modell_perf.py, Quadrik)' % (len(In) // 3, vorher),
          'ecken': len(En), 'indizes': len(In), 'indexAb': En.nbytes + pad, 'teile': teile}
    with open(os.path.join(d, 'auto_perf.bin'), 'wb') as f:
        f.write(En.tobytes()); f.write(b'\0' * pad); f.write(In.tobytes())
    json.dump(pm, open(os.path.join(d, 'auto_perf.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    meta['perf'] = 'auto_perf'
    json.dump(meta, open(os.path.join(d, 'auto.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(d, pm['lod'], 'Datei %.1f MB' % (os.path.getsize(os.path.join(d, 'auto_perf.bin')) / 1e6))


if __name__ == '__main__':
    main()
