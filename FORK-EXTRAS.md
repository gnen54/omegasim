# Fork-Extras (gnen54/omegasim, Zweig testversion)

Diese Erweiterungen gehören zu Günters Fork und müssen nach JEDEM Update von Luuke in der
Testfassung (Zweig `testversion`) vorhanden sein. Günter entwickelt das virtuelle Fahren nur noch
im Fork (keine PRs an Luuke mehr); Ziel ist eine Fassung, die am **PC** gut aussieht und gut fährt.
Hat Luuke etwas selbst geändert oder weggelassen, gilt in der Testfassung die Fork-Lösung.

Stand: 23.11.2026 (auf Luukes 1.6.22). Garagen-Menü (Garage: links „Virtuell fahren“, rechts die Einstellungen; Kachel „Virtuell fahren“ im FAHREN-Menü) ist Luukes allgemeiner Garagen-Code (90-ghosts.js, 51-konsole.js) und bleibt von ihm. Ältere Fassung: Zweig `sicherung-testversion-1.4.67`.

## Aufbau: das virtuelle Fahren ist ganz unseres (seit 23.11.2026)

- **Günters Entscheidung (23.11.):** „Ich möchte NUR unseren Stand Virtuelles Fahren erhalten. Bisher war ich zufrieden.“
  Darum ist **`src/60d-virtuell.js` die Fork-Fassung** (Stand 22.11. aus `sicherung-testversion-1.4.67`, plus
  Korrekturen danach). Luukes Änderungen am virtuellen Fahren (seine 60d-virtuell.js) werden **nicht** übernommen:
  keine Lackfarben-Palette, Tageszeit, 3D-Regen, TV-Kamera, Bildraten-Wache, LibreCorsa-Handling im VF, Ladebild
  mit Karte, Piktogramm-Knopfleiste, flacher Rückspiegel usw.
- **Alles andere** (Rennen, Ansagen, DualSense, Physik-Kern, Optionen …) kommt weiter von Luuke.
- Luukes Selbsttests für SEINE Fahr-Neuerungen sind in `src/95-selftest.js` entfernt (Kommentarzeile
  „Fork gnen54: Luukes Test … entfernt“); unsere VF-Tests stehen am Ende unter „Fork gnen54: Selbsttests des
  virtuellen Fahrens“. Bekannt rot wie schon in der alten Fork-Fassung: „Virtuell v1.3.122: Kamera-Knopf …“
  (unser Ladebild zeigt die Strecke von oben, solange die Autos laden).
- Unser Ladeschild heißt `vf-laden-fork` (Luukes CSS für `.vf-laden` würde es verziehen).
- **Bei einem Update von Luuke:** `src/60d-virtuell.js` und `hilfe/virtuelles-fahren.html` IMMER aus der bisherigen
  testversion behalten. Ruft Luukes übriger Code neue VF-Funktionen auf, die es bei uns nicht gibt, oder ändert er
  Funktionen, die unser VF benutzt (Physik, Pad, Rennen, Ton), dann nur die Schnittstelle anpassen, nie Luukes
  VF-Datei übernehmen. Neue Luuke-Selbsttests, die nur sein VF prüfen, entfernen (wie oben).
- Startampel und Akku kritisch kommen weiter aus den Zweigen `startampel` und `akku-kritisch` (Merge).

## Liste (jede Zeile wird vor dem Hochladen mit `git grep -F` geprüft)

| Erweiterung | Wo | Prüfung (muss gefunden werden) |
|---|---|---|
| Unser virtuelles Fahren (ganze Datei) | `src/60d-virtuell.js`, `hilfe/virtuelles-fahren.html` | `vf-laden-fork`, `const VF_COCKPIT_FOVH` |
| Startampel am Tisch (AddOn-Menü, BLE) | `src/74-startampel.js`, `src/00-index.head.html` (#tab-addon) | `AMPEL_STAND`, `id="tab-addon"` |
| Startansage „Gentlemen, start your engines“ | `src/80-sound.js`, Schalter `setting-announce-start` | `setting-announce-start` |
| Akku kritisch (6 %, „Session abbrechen, Box anfahren!“) | `src/80-sound.js`, Schalter `setting-announce-battery-crit` | `setting-announce-battery-crit`, `AKKU_KRITISCH` |
| ansageAn mit `start: true, batterycrit: true` | `src/80-sound.js` | `start: true, batterycrit: true` |
| Opel Manta B400 (nur Fork, KEINE Freigabe, nie in einen PR) | `img/autos/manta/`, Fork-Datei | `manta: 'img/autos/manta/'`, `{ v: 'manta'` |
| Porsche 911 GT3 (nur Fork, Freigabe nur mündlich) | `img/autos/gt3/`, Fork-Datei | `gt3: 'img/autos/gt3/'`, `{ v: 'gt3'` |
| Feste Motorklänge Manta/GT3 (+ Menü, Doku, SAMPLE_CARS, Garagen-Name) | `audio/loops.json`, `audio/*.ogg`, `src/80-sound.js`, `src/00-index.head.html`, `tools/engine_synth.py`, `audio/CREDITS.md`, `src/60d-virtuell.js` | `manta400_rec`, `sd_boxer_dunkel`, `const festNamen` |
| Freie Strecke Heckenhoim (nur Fork) | `img/strecken/heckenhoim.json`, `src/60d-virtuell.js` | `heckenhoim: { name: 'Heckenhoim'` |
| Boden „Stein grau marmoriert“ | `src/60d-virtuell.js` | `id: 'stein'`, `function vfSteinZeilen` |
| Bestzeiten je Strecke und Auto (Garage, aufklappbar) | `src/60d-virtuell.js` | `VF_ZEITEN_STORE`, `function vfBestenliste`, `vfZeitMerken(VF.letzte` |
| Seitennahe Kamera | `src/60d-virtuell.js` | `id: 'naeher'`, `naeher = id === 'naeher'` |
| Leichte Modelle für Performance (auto.json "perf") | `src/60d-virtuell.js`, `img/autos/*/auto_perf.*` | `meta.perf`, `"perf": "auto_perf"` |
| Handy/Tablet nur Performance, Hinweis „Quality nur am PC verfügbar“ | `src/60d-virtuell.js` | `function vfMobilGeraet`, `Quality nur am PC verfügbar` |
| Garage: Vorschaubild des Autos + Lackfarbe mit 9 Farbpunkten (nach Luukes v1.5.10, 23.11.; nur der Grundlack wird umgefärbt, Streifen bleiben) | `src/60d-virtuell.js` (VF_LACK_FARBEN, Shader-Uniform `lack`, `M.hauptLack`), Selbsttest am Ende von 95 | `const VF_LACK_FARBEN`, `const hauptLack`, `mix(tint, pow(tint, vec3(2.2)), lack)`, `Fork 23.11.): Garage zeigt Vorschaubild` |
| Bulli: Scheiben von innen fast klar (Onboard-Kamera) | `src/60d-virtuell.js` | `innen ? 0.12 : 0.86` |
| Innenspiegel, Außenspiegel (Spider), Armaturenbrett-Cockpit wie im Fork | `src/60d-virtuell.js` | `function vfInnenspiegelMalen`, `function vfCockpit(` |
| Umgebungston (Ambience) ab Werk aus | `src/80-sound.js`, `id="amb-enable"` ohne checked | `let ambienceEnabled = false` |
| Freigaben-Liste „Eigene Autos von Gnen54 und die Freigaben“ | `src/00-index.head.html` (Credits) | `Eigene Autos von Gnen54 und die Freigaben` |
| Testfassung holt Seite/HTML/JSON mit no-cache | `tools/sw.js.in` | `cache: 'no-cache'` |
| Vorschaubilder mit echter 3D-Grafik (WebGL) | `img/autos/{caravelle,spider,gt3,manta,kaefer}/vorschau.jpg`, Werkzeug `tools/vorschau_webgl/` | `function zeichne(auto)` — neue oder geänderte Modelle damit neu zeichnen (`python3 -m http.server 8790` im Repo, dann `node tools/vorschau_webgl/erzeugen.js <autos>`), NICHT mit `tools/vorschau_bilder.py` (fleckig) |
| Selbsttests Fork | `src/95-selftest.js` (Ende) | `Fork gnen54: Selbsttests des virtuellen Fahrens`, `Performance laedt die leichte Fassung` |
| Übersetzungen (EN/ES) aller Fork-Texte | `src/10-ble-explorer.js` | `Stein grau marmoriert`, `Opel Manta B400 (Gnen54, WIP)` |

Nicht mehr in der Testfassung: Ruckel-Testseiten u1-u5.html.
