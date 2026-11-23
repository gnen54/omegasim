# Fork-Extras (gnen54/omegasim, Zweig testversion)

Diese Erweiterungen gehören zu Günters Fork und müssen nach JEDEM Update von Luuke in der
Testfassung (Zweig `testversion`) vorhanden sein. Günter entwickelt das virtuelle Fahren nur noch
im Fork (keine PRs an Luuke mehr); Ziel ist eine Fassung, die am **PC** gut aussieht und gut fährt.
Hat Luuke etwas selbst geändert oder weggelassen, gilt in der Testfassung die Fork-Lösung.

Stand: 23.11.2026 (auf Luukes 1.6.22). Ältere Fassung: Zweig `sicherung-testversion-1.4.67`.

## Aufbau: Fork-Code getrennt von Luukes Code

- **`src/98z-fork-gnen54.js`** enthält alles Fork-Eigene am virtuellen Fahren: Einträge in Luukes Listen
  (Boden, Autos, Motoren, Strecken, Kameras), eigene Funktionen, ersetzte Funktionen und Fork-Selbsttests.
  Die Datei wird als letzte vor dem Schluss des gemeinsamen Gültigkeitsbereichs geladen.
- **`src/60d-virtuell.js`** bleibt Luukes Datei, nur mit wenigen **Einhängepunkten**: einzeilige Aufrufe
  `if (typeof vfForkXxx === 'function') ...` mit dem Kommentar `Fork-Einhaengepunkt (98z-fork-gnen54.js)`.
  Bei einem Update von Luuke: seine Datei übernehmen und nur diese Zeilen wieder einsetzen
  (`git grep -n vfFork src/60d-virtuell.js` in der alten testversion zeigt sie).
- **Ersetzte Funktionen** (Liste `VF_FORK_ERSETZT` in der Fork-Datei): von Luukes Fassung ist ein
  Fingerabdruck in `tools/fork/fingerabdruecke.json` gespeichert. **`python3 tools/fork_pruefen.py`** meldet,
  wenn Luuke eine davon geändert hat oder ein Einhängepunkt fehlt. Dann Luukes neue Fassung ansehen, Sinnvolles
  in die Fork-Fassung übernehmen und `python3 tools/fork_pruefen.py --merken`.
- Startampel und Akku kritisch kommen weiter aus den Zweigen `startampel` und `akku-kritisch` (Merge).
- Kleine HTML/Wörterbuch-/Klang-Ergänzungen stehen noch in Luukes Dateien (reine Einfügungen, selten Konflikte).

## Liste (jede Zeile wird vor dem Hochladen mit `git grep -F` geprüft)

| Erweiterung | Wo | Prüfung (muss gefunden werden) |
|---|---|---|
| Fork-Datei und Prüfwerkzeug | `src/98z-fork-gnen54.js`, `tools/fork_pruefen.py`, `tools/fork/fingerabdruecke.json` | `VF_FORK_ERSETZT`, `def abdruck` |
| Startampel am Tisch (AddOn-Menü, BLE) | `src/74-startampel.js`, `src/00-index.head.html` (#tab-addon) | `AMPEL_STAND`, `id="tab-addon"` |
| Startansage „Gentlemen, start your engines“ | `src/80-sound.js`, Schalter `setting-announce-start` | `setting-announce-start` |
| Akku kritisch (6 %, „Session abbrechen, Box anfahren!“) | `src/80-sound.js`, Schalter `setting-announce-battery-crit` | `setting-announce-battery-crit`, `AKKU_KRITISCH` |
| ansageAn mit `start: true, batterycrit: true` | `src/80-sound.js` | `start: true, batterycrit: true` |
| Opel Manta B400 (nur Fork, KEINE Freigabe, nie in einen PR) | `img/autos/manta/`, Fork-Datei | `manta: 'img/autos/manta/'`, `{ v: 'manta'` |
| Porsche 911 GT3 (nur Fork, Freigabe nur mündlich) | `img/autos/gt3/`, Fork-Datei | `gt3: 'img/autos/gt3/'`, `{ v: 'gt3'` |
| Feste Motorklänge Manta/GT3 (+ Menü, Doku, SAMPLE_CARS, Garagen-Name) | `audio/loops.json`, `audio/*.ogg`, `src/80-sound.js`, `src/00-index.head.html`, `tools/engine_synth.py`, `audio/CREDITS.md`, Fork-Datei | `manta400_rec`, `sd_boxer_dunkel`, `function vfForkFestName` |
| Freie Strecke Heckenhoim (nur Fork) | `img/strecken/heckenhoim.json`, Fork-Datei | `VF_FREIE.heckenhoim` |
| Boden „Stein grau marmoriert“ | Fork-Datei (Eintrag, vfSteinZeilen, ersetzte vfBodenBau/vfBodenGeometrie) | `id: 'stein'`, `function vfSteinZeilen` |
| Bestzeiten je Strecke und Auto (Garage, aufklappbar) | Fork-Datei + Einhängepunkte | `VF_ZEITEN_STORE`, `function vfBestenliste`, `vfForkRunde();`, `vfForkStart();`, `vfForkGarageEnde(rechts, autos);` |
| Seitennahe Kamera | Fork-Datei + Einhängepunkt in vfKameraBasis | `id: 'naeher'`, `vfForkKameraNaeher(fx, fz, dt, art, D)` |
| Leichte Modelle für Performance (auto.json "perf") | Fork-Datei (ersetzte vfModellDaten), `img/autos/*/auto_perf.*` | `meta.perf`, `"perf": "auto_perf"` |
| Handy/Tablet nur Performance, Hinweis „Quality nur am PC verfügbar“ | Fork-Datei (vfMobilGeraet, ersetzte vfGrafik, Einhängepunkt Grafik-Zeile) | `function vfMobilGeraet`, `vfForkGrafikZeile(grafikZeile);` |
| Bulli: Scheiben von innen fast klar (Onboard-Kamera) | Fork-Datei + Einhängepunkt im Modell-Zeichnen | `glasInnen ? 0.12 : 0.86`, `function vfForkGlasInnen` |
| Innen-Rückspiegel in Fork-Größe (30 % Breite, Höhe 27 % der Breite) | Fork-Datei (ersetzte vfSpiegelRechtecke, Prüf-Hülle um Luukes Spiegeltest) | `sw * 0.27`, `Fork: Spiegelhoehe wie im Fork` |
| Umgebungston (Ambience) ab Werk aus | `src/80-sound.js`, `id="amb-enable"` ohne checked | `let ambienceEnabled = false` |
| Freigaben-Liste „Eigene Autos von Gnen54 und die Freigaben“ | `src/00-index.head.html` (Credits) | `Eigene Autos von Gnen54 und die Freigaben` |
| Testfassung holt Seite/HTML/JSON mit no-cache | `tools/sw.js.in` | `cache: 'no-cache'` |
| Vorschaubilder mit echter 3D-Grafik (WebGL) | `img/autos/{caravelle,spider,gt3,manta,kaefer}/vorschau.jpg`, Werkzeug `tools/vorschau_webgl/` | `function zeichne(auto)` — neue oder geänderte Modelle damit neu zeichnen (`python3 -m http.server 8790` im Repo, dann `node tools/vorschau_webgl/erzeugen.js <autos>`), NICHT mit `tools/vorschau_bilder.py` (fleckig) |
| Selbsttests Fork | Fork-Datei | `Performance laedt die leichte Fassung`, `auf Handy und Tablet nur Performance` |
| Übersetzungen (EN/ES) aller Fork-Texte | `src/10-ble-explorer.js` | `Stein grau marmoriert`, `Opel Manta B400 (Gnen54, WIP)` |

Bewusst bei Luukes Lösung gelassen (Stand 23.11.): Ladebild, Knopfleiste, Geist (bei Luuke ab Werk an),
kein Armaturenbrett-Cockpit, Rückspiegel-Ort ganz oben mittig. Nicht mehr in der Testfassung: Ruckel-Testseiten u1-u5.html.
