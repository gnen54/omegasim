"""Heckenhoim (Renn-Rollstrecke, 3 x 2 m, Gnen54) -> img/strecken/heckenhoim.json.
DXF seit 22.11.2026: Heckenhoim_V2 aus Thorstens Fusion-Projekt, Basis auf 3 x 2 m korrigiert -> Faktor 1.
Ablauf wie bei der Toernerschleife (ring2_bau / ring2_mitte / ring2_json / bucht_tiefe / boxgasse), hier in einem Skript.
Fahrtrichtung (22.11., Thorsten/Startaufstellung im Bild): auf der linken Geraden nach oben, wie der Pfeil
in der DXF (Boxengasse unten rein, oben raus)."""
import sys, json, numpy as np, cv2, networkx as nx
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dxfread import lies
from scipy.ndimage import distance_transform_edt, uniform_filter1d
from scipy.spatial import cKDTree
from skimage.morphology import skeletonize

s, _ = lies(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'heckenhoim.dxf')); s = [P * 1.0 for P in s]
R = 2.0; X0, Y0, W, H = -1500, -1000, 3000, 2000
RAHMEN = {0, 1, 2, 12, 13}                       # Rahmen, Diagonalen, Fahrtrichtungspfeil
MARKEN = {5, 6}                                  # kleine Rechtecke an Ein- und Ausfahrt der Gasse
START_RECHTECK = {4}
px = lambda P: np.c_[(P[:, 0] - X0) / R, (Y0 + H - P[:, 1]) / R]
rc = lambda p: (int(round((Y0 + H - p[1]) / R)), int(round((p[0] - X0) / R)))
mm = lambda r: np.array([r[1] * R + X0, Y0 + H - r[0] * R])

def raster(ohne):
    img = np.zeros((int(H / R), int(W / R)), np.uint8)
    for j, P in enumerate(s):
        if j in RAHMEN or j in ohne: continue
        cv2.polylines(img, [np.round(px(P)).astype(np.int32)], False, 255, 2)
    return img
def fuellen(img, p):
    f = img.copy(); m = np.zeros((f.shape[0] + 2, f.shape[1] + 2), np.uint8)
    r, c = rc(p); cv2.floodFill(f, m, (c, r), 128); return f == 128

haupt = fuellen(raster(START_RECHTECK), (0, 850))                 # Hauptbahn (Gasse durch die Marken zu)
alles = fuellen(raster(START_RECHTECK | MARKEN), (0, 850))        # mit Boxengasse
haupt = cv2.morphologyEx(haupt.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)).astype(bool)
alles = cv2.morphologyEx(alles.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)).astype(bool)
steg = fuellen(raster(set()), (-1080, 0))
print('Hauptbahn %.2f m2, mit Gasse %.2f m2, Steg %.0f cm2' % (haupt.sum() * R * R / 1e6, alles.sum() * R * R / 1e6, steg.sum() * R * R / 100))

# ---- Mittellinie: Skelett der Hauptbahn, groesster Kreis
dt = distance_transform_edt(haupt)
sk = skeletonize(haupt)
pts = np.argwhere(sk); idx = {tuple(p): i for i, p in enumerate(pts)}
G = nx.Graph()
for i, (r, c) in enumerate(pts):
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            j = idx.get((r + dr, c + dc))
            if j is not None and j > i: G.add_edge(i, j, weight=np.hypot(dr, dc))
zyk = max(nx.cycle_basis(G), key=len)
M = np.array([mm(pts[i]) for i in zyk])
# Ordnung entlang des Kreises (cycle_basis liefert die Knoten in Kreisreihenfolge)
for _ in range(4): M = np.c_[uniform_filter1d(M[:, 0], 21, mode='wrap'), uniform_filter1d(M[:, 1], 21, mode='wrap')]
# Fahrtrichtung: auf der linken Geraden (x < -1100) nach oben (Pfeil in der DXF)
links = np.where((M[:, 0] < -1150) & (np.abs(M[:, 1]) < 300))[0]
dy = np.mean(np.diff(M[links, 1])) if len(links) > 2 else 0
if dy < 0: M = M[::-1]
breite = 2 * np.median(dt[sk]) * R
start_mm = np.array([(-1447 + -1111.5) / 2, (126 + 150) / 2.0])
print('Laenge %.2f m, Breite (Skelett) %.0f mm' % (np.hypot(*np.diff(np.vstack([M, M[:1]]), axis=0).T).sum() / 1000, breite))

BREITE = 336.0                                     # Startlinie quer ueber die Bahn = Bahnbreite
K = 25.0 / BREITE * 0.997                          # Karteneinheiten je mm (Bahn = 25 Einheiten wie die Toernerschleife)
P_ = np.vstack([M, M[:1]]); sl = np.r_[0, np.cumsum(np.hypot(*np.diff(P_, axis=0).T))]
u = np.arange(0, sl[-1], 2.857 / K); M = np.c_[np.interp(u, sl, P_[:, 0]), np.interp(u, sl, P_[:, 1])]
r0 = int(np.argmin(np.hypot(*(M - start_mm).T))); M = np.roll(M, -r0, axis=0)
ed = lambda Q: np.c_[Q[:, 0] * K, -Q[:, 1] * K]
E = ed(M)
t = np.roll(E, -1, axis=0) - np.roll(E, 1, axis=0); t /= np.linalg.norm(t, axis=1)[:, None]
nrm = np.c_[t[:, 1], -t[:, 0]]                     # Editor: quer > 0 = links
nmm = np.c_[nrm[:, 0], -nrm[:, 1]]
# Seite der Gasse und Boxenabschnitt: Punkte, deren Normale (eine Seite) innerhalb 260 mm auf den Steg trifft
sk_steg = np.argwhere(skeletonize(steg)); S = np.array([mm(p) for p in sk_steg])
o = [int(np.argmax(S[:, 1]))]; rest = set(range(len(S))) - {o[0]}; T = cKDTree(S)
while rest:
    d_, j_ = T.query(S[o[-1]], k=12); nxt = [jj for jj in j_ if jj in rest]
    if not nxt: break
    o.append(nxt[0]); rest.discard(nxt[0])
S = S[o]
def trifft(i, sg, bis=300):
    for dmm in np.arange(0, bis, 2.0):
        q = M[i] + nmm[i] * dmm * sg; r, c = rc(q)
        if 0 <= r < steg.shape[0] and 0 <= c < steg.shape[1] and steg[r, c]: return dmm
    return None
gasse = alles & ~haupt
gasse = cv2.morphologyEx(gasse.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)).astype(bool)
# 21.11. (GEMELDET Gnen54: "Boxengasse viel zu schmal, da passt kein Fahrzeug drauf"): in der DXF 73 mm
# = gut 5 Karteneinheiten, ein Auto ist ~4 breit. Die Gasse waechst um BREIT_MM nach aussen in die Insel,
# mit mindestens 25 mm Abstand zur Bahn dahinter.
BREIT_MM = 0    # 75 = verbreiterte Gasse (Test 21.11., nicht gepusht); 0 = wie in der DXF
hd0 = distance_transform_edt(~haupt) * R
ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * int(BREIT_MM / R) + 1,) * 2)
# Aussenkante im festen Abstand zum Steg (nicht zur alten Wand), sonst wellt sie sich und schlaegt an den
# Enden Haken; danach rund glaetten.
sdst = distance_transform_edt(~steg) * R
breit = cv2.dilate(gasse.astype(np.uint8), ker).astype(bool) & ~steg & (hd0 > 25) & (sdst <= 73 + BREIT_MM)
rund = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31))
breit = cv2.morphologyEx(cv2.morphologyEx(breit.astype(np.uint8), cv2.MORPH_OPEN, rund), cv2.MORPH_CLOSE, rund).astype(bool)
breit &= ~alles & ~steg & (hd0 > 25)
alles = alles | breit
gasse = gasse | breit
HALF = 12.5
def strahl(i, sg):
    letzte, leer, gesehen = 0, 0, False
    for dmm in np.arange(0, 800, 2.0):
        q = M[i] + nmm[i] * dmm * sg; r, c = rc(q)
        if not (0 <= r < gasse.shape[0] and 0 <= c < gasse.shape[1]): break
        if gasse[r, c]: letzte, gesehen, leer = dmm, True, 0
        elif steg[r, c] or haupt[r, c]: leer = 0
        else:
            leer += 2
            if leer > 10: break
    return letzte if gesehen else 0
best = None
for sg in (1, -1):
    tt = np.array([strahl(i, sg) for i in range(len(M))])
    if best is None or (tt > 0).sum() > (best[1] > 0).sum(): best = (sg, tt)
SEITE, tief = best
x = np.where(tief > 0, np.maximum(0, tief * K - HALF), 0.0); x[x < 1.5] = 0
x = uniform_filter1d(uniform_filter1d(x, 9, mode='wrap'), 9, mode='wrap')
x[x < 0.05] = 0
ii = np.where(x > 0)[0]
if len(ii) and ii[0] == 0 and ii[-1] == len(x) - 1:
    k0 = int(np.where(np.diff(ii) > 1)[0][0]) + 1; ii = np.r_[ii[k0:], ii[:k0]]
for k_, f in enumerate([1 / 4, 2 / 4, 3 / 4]):
    if len(ii) > 6: x[ii[k_]] *= f; x[ii[-1 - k_]] *= f

on = x > 0
n_ = len(x); b1 = int(np.where(on)[0][on[np.where(on)[0]].argmax()]) if on.any() else 0
# Lauf durch Index 0: Anfang = erster Punkt einer zusammenhaengenden Folge, die ueber das Ende laeuft
b0 = n_ - 1
while on[b0 - 1]: b0 -= 1
print('Gasse vor dem Start ab', b0, 'von', n_, ', nach dem Start bis', int(np.argmin(on)) - 1)
tiles, tile_of = [], np.zeros(len(E), int); i = 0
while i < len(E):
    if i == b0:
        tiles.append('PIT'); tile_of[b0:] = len(tiles) - 1; break
    jj = min(len(E), i + 14, b0 if i < b0 else len(E))
    tiles.append('START' if i == 0 else 'STRAIGHT'); tile_of[i:jj] = len(tiles) - 1; i = jj
versatz = (E.max(0) + E.min(0)) / 2; E = E - versatz
edv = lambda Q: ed(Q) - versatz
out = {'name': 'Heckenhoim', 'quelle': 'Heckenhoim_V2.dxf (Gnen54/Thorsten), 3,00 x 2,00 m',
       'breiteMm': BREITE, 'kacheln': tiles,
       'pts': [[round(float(a), 2), round(float(b_), 2), int(tl)] for (a, b_), tl in zip(E, tile_of)]}
Sm = edv(S); step = max(1, len(Sm) // 160)
out['steg'] = {'b': round(float(steg.sum() * R * R / (np.hypot(*np.diff(S, axis=0).T).sum() + 1) * K), 2),
               'pts': [[round(float(a), 2), round(float(b_), 2)] for a, b_ in Sm[::step]]}
out['boxBucht'] = round(float(np.median(x[x > 0]) / 11.63), 2) if (x > 0).any() else 1.0
out['boxSeite'] = int(SEITE)
gz = np.argwhere(gasse); gm = mm(gz[len(gz) // 2])
out['boxPunkt'] = [round(float(v), 2) for v in edv(gm[None])[0]]
out['buchtPkt'] = [round(float(v), 2) for v in x]
out['_versatz'] = [round(float(versatz[0]), 3), round(float(versatz[1]), 3)]
# Gasse als Dreiecke (Ear clipping) + Wandlinien (Kontur an Gras, nicht an Hauptbahn oder Steg)
# Muendungen: die Gasse reicht bis an das gefahrene Band (halbe Bahn um die Mittellinie), sonst bleibt
# zwischen Gasse und Bahn ein Streifen Gras (die DXF-Bahn ist dort breiter als das Band).
mimg = np.full(haupt.shape, 255, np.uint8)
cv2.polylines(mimg, [np.round(px(np.vstack([M, M[:1]]))).astype(np.int32)], False, 0, 1)
dmitte = distance_transform_edt(mimg) * R
HALB_MM = HALF / K
kand = (alles & ~steg & (dmitte > HALB_MM - 10)).astype(np.uint8)
n_k, lab_k = cv2.connectedComponents(kand, connectivity=4)
ids = np.unique(lab_k[gasse & (lab_k > 0)])
gasse = (np.isin(lab_k, ids) & (lab_k > 0)) | (gasse & ~steg)
print('Gasse mit Muendungen %.0f cm2' % (gasse.sum() * R * R / 100))
gasse = cv2.morphologyEx(gasse.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)).astype(bool)
gd = (cv2.dilate(gasse.astype(np.uint8), np.ones((5, 5), np.uint8)) & alles.astype(np.uint8))
n_l, lab = cv2.connectedComponents(gd, connectivity=8)
gd = (lab == np.bincount(lab.ravel())[1:].argmax() + 1).astype(np.uint8)
cs, _ = cv2.findContours(gd, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
c = max(cs, key=cv2.contourArea); c = cv2.approxPolyDP(c, 1.2, True)[:, 0, :].astype(float)
poly = np.c_[c[:, 0] * R + X0, Y0 + H - c[:, 1] * R]
def flaeche(Q): return 0.5 * np.sum(Q[:, 0] * np.roll(Q[:, 1], -1) - np.roll(Q[:, 0], -1) * Q[:, 1])
Q = poly if flaeche(poly) > 0 else poly[::-1]
idx2 = list(range(len(Q))); tri = []
def innen(p, a, b_, c_):
    def s_(p1, p2, p3): return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])
    d1, d2, d3 = s_(p, a, b_), s_(p, b_, c_), s_(p, c_, a)
    return not ((d1 < 0 or d2 < 0 or d3 < 0) and (d1 > 0 or d2 > 0 or d3 > 0))
guard = 0
while len(idx2) > 3 and guard < 200000:
    guard += 1; ok = False
    for k_ in range(len(idx2)):
        i0, i1, i2 = idx2[k_ - 1], idx2[k_], idx2[(k_ + 1) % len(idx2)]
        a, b_, c_ = Q[i0], Q[i1], Q[i2]
        if (b_[0] - a[0]) * (c_[1] - a[1]) - (b_[1] - a[1]) * (c_[0] - a[0]) <= 0: continue
        if any(innen(Q[j], a, b_, c_) for j in idx2 if j not in (i0, i1, i2)): continue
        tri.append((i0, i1, i2)); idx2.pop(k_); ok = True; break
    if not ok: break
if len(idx2) == 3: tri.append(tuple(idx2))
print('Gasse: %d Ecken, %d Dreiecke, Rest %d' % (len(Q), len(tri), len(idx2)))
EQ = edv(Q)
out['boxDreiecke'] = [round(float(v), 2) for t_ in tri for j in t_ for v in EQ[j]]
sd = distance_transform_edt(~steg) * R; hd = distance_transform_edt(~haupt) * R
cc = max(cv2.findContours(gd, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[0], key=cv2.contourArea)[:, 0, :]
wand = np.array([dmitte[y, x_] > HALB_MM + 14 and sd[y, x_] > 8 for x_, y in cc])
linien, akt = [], []
for (x_, y), w in zip(cc, wand):
    if w: akt.append((x_ * R + X0, Y0 + H - y * R))
    elif len(akt) > 5: linien.append(np.array(akt)); akt = []
    else: akt = []
if len(akt) > 5: linien.append(np.array(akt))
out['boxRand'] = [[[round(float(a), 2), round(float(b_), 2)] for a, b_ in edv(L[::3])] for L in linien if len(L[::3]) >= 3]
print('Randlinien', [len(l) for l in out['boxRand']], 'Bucht max %.1f' % x.max(), 'Steg b', out['steg']['b'])
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'img', 'strecken', 'heckenhoim.json'), 'w'), separators=(',', ':'))

