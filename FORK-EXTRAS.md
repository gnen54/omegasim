# Fork-Extras (gnen54/omegasim, Zweig testversion)

Diese Erweiterungen gehören zu Günters Fork und müssen nach JEDEM Update von Luuke in der
Testfassung (Zweig `testversion`) wieder vorhanden sein. Hat Luuke etwas davon selbst übernommen,
gilt seine Fassung, aber die Funktion muss bleiben. Die tägliche Pflege prüft jede Zeile mit dem
angegebenen Suchbegriff (`git grep`), bevor sie `testversion` hochlädt.

Stand: 23.11.2026 (auf Luukes 1.6.22). Vollständige alte Fassung: Zweig `sicherung-testversion-1.4.67`.

| Erweiterung | Wo | Prüfung (muss gefunden werden) |
|---|---|---|
| Startampel am Tisch (AddOn-Menü, BLE) | `src/74-startampel.js`, `src/00-index.head.html` (#tab-addon) | `AMPEL_STAND`, `id="tab-addon"` |
| Startansage „Gentlemen, start your engines“ | `src/80-sound.js`, Schalter `setting-announce-start` | `setting-announce-start` |
| Akku kritisch (6 %, „Session abbrechen, Box anfahren!“) | `src/80-sound.js`, Schalter `setting-announce-battery-crit` | `setting-announce-battery-crit`, `AKKU_KRITISCH` |
| ansageAn mit `start: true, batterycrit: true` | `src/80-sound.js` | `start: true, batterycrit: true` |
| Opel Manta B400 (nur Fork, KEINE Freigabe, nie in einen PR) | `img/autos/manta/`, `src/60d-virtuell.js` | `manta: 'img/autos/manta/'`, `{ v: 'manta'` |
| Porsche 911 GT3 (nur Fork, Freigabe nur mündlich) | `img/autos/gt3/`, `src/60d-virtuell.js` | `gt3: 'img/autos/gt3/'`, `{ v: 'gt3'` |
| Feste Motorklänge Manta/GT3 (+ Menü, Doku, SAMPLE_CARS) | `audio/loops.json`, `audio/*.ogg`, `src/80-sound.js`, `src/00-index.head.html`, `tools/engine_synth.py`, `audio/CREDITS.md` | `manta400_rec`, `sd_boxer_dunkel` |
| Freie Strecke Heckenhoim (nur Fork) | `img/strecken/heckenhoim.json`, `VF_FREIE` | `heckenhoim: { name: 'Heckenhoim'` |
| Boden „Stein grau marmoriert“ | `src/60d-virtuell.js` (VF_BOEDEN, vfSteinZeilen, art 'flaeche') | `id: 'stein'`, `function vfSteinZeilen` |
| Bestzeiten je Strecke und Auto (Garage, aufklappbar) | `src/60d-virtuell.js` | `VF_ZEITEN_STORE`, `function vfBestenliste`, `vfZeitMerken(VF.letzte` |
| Seitennahe Kamera | `src/60d-virtuell.js` (VF_KAMERAS, Kamera-Basis) | `id: 'naeher'`, `naeher = id === 'naeher'` |
| Leichte Modelle für Performance (auto.json "perf") | `src/60d-virtuell.js` (vfModellDaten), `img/autos/*/auto_perf.*` | `meta.perf`, `"perf": "auto_perf"` |
| Handy/Tablet nur Performance, Hinweis „Quality nur am PC verfügbar“ | `src/60d-virtuell.js` | `function vfMobilGeraet`, `Quality nur am PC verfügbar` |
| Bulli: Scheiben von innen fast klar (Onboard-Kamera) | `src/60d-virtuell.js` (Glas im Modell-Zeichnen) | `innen ? 0.12 : 0.86` |
| Innen-Rückspiegel in Fork-Größe (30 % Breite, Höhe 27 % der Breite) | `src/60d-virtuell.js` (vfSpiegelRechtecke) + 2 Selbsttests | `sw * 0.27` |
| Umgebungston (Ambience) ab Werk aus | `src/80-sound.js`, `id="amb-enable"` ohne checked | `let ambienceEnabled = false` |
| Freigaben-Liste „Eigene Autos von Gnen54 und die Freigaben“ | `src/00-index.head.html` (Credits) | `Eigene Autos von Gnen54 und die Freigaben` |
| Testfassung holt Seite/HTML/JSON mit no-cache | `tools/sw.js.in` | `cache: 'no-cache'` |
| Vorschaubilder mit echter 3D-Grafik (WebGL) | `img/autos/{caravelle,spider,gt3,manta,kaefer}/vorschau.jpg`, Werkzeug `tools/vorschau_webgl/` | `function zeichne(auto)` in `tools/vorschau_webgl/render.html`; neue oder geänderte Modelle damit neu zeichnen (`python3 -m http.server 8790` im Repo, dann `node tools/vorschau_webgl/erzeugen.js <autos>`), NICHT mit `tools/vorschau_bilder.py` (fleckig) |
| Selbsttests Fork | `src/95-selftest.js` | `Performance laedt die leichte Fassung`, `auf Handy und Tablet nur Performance` |
| Übersetzungen (EN/ES) aller Fork-Texte | `src/10-ble-explorer.js` | `Stein grau marmoriert`, `Opel Manta B400 (Gnen54, WIP)` |

Bewusst bei Luukes Lösung gelassen (Stand 23.11.): Ladebild, Knopfleiste, Geist (bei Luuke ab Werk an),
kein Armaturenbrett-Cockpit, Rückspiegel-Ort ganz oben mittig. Nicht mehr in der Testfassung: Ruckel-Testseiten u1-u5.html.
