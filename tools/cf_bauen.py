#!/usr/bin/env python3
"""Build-Schritt fuer Cloudflare Pages (privater Zugang, 28.11.2026).

Cloudflare Pages nimmt keine Datei ueber 25 MiB. Dieses Skript laeuft dort als Build-Befehl
(`python3 tools/cf_bauen.py`, Ausgabeverzeichnis `/`):
- grosse Modelldateien (img/autos/*/*.bin) werden in Teile zu 20 MiB zerlegt
  (auto.teil0.bin, auto.teil1.bin, ... plus auto.teile.json mit der Anzahl), das Original entfaellt;
  60d-virtuell.js setzt sie beim Laden wieder zusammen, wenn auto.bin fehlt.
- apk/OmegaSim.apk (Lukes App, im Browser nicht gebraucht) entfaellt.
Im Repo selbst aendert sich nichts."""
import glob, json, os

GRENZE = 24 * 1024 * 1024
TEIL = 20 * 1024 * 1024
for f in sorted(glob.glob('img/autos/*/*.bin')):
    n = os.path.getsize(f)
    if n <= GRENZE: continue
    basis = f[:-4]
    with open(f, 'rb') as q:
        k = 0
        while True:
            b = q.read(TEIL)
            if not b: break
            open('%s.teil%d.bin' % (basis, k), 'wb').write(b); k += 1
    json.dump({'teile': k, 'bytes': n}, open(basis + '.teile.json', 'w'))
    os.remove(f)
    print('zerlegt', f, n, '->', k, 'Teile')
for f in glob.glob('apk/*.apk'):
    os.remove(f); print('entfernt', f)
