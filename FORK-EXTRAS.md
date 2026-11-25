# Fork-Extras (gnen54/omegasim, Zweig testversion)

Diese Erweiterungen gehören zu Günters Fork und müssen nach JEDEM Update von Luuke in der
Testfassung (Zweig `testversion`) vorhanden sein. Günter entwickelt das virtuelle Fahren nur noch
im Fork (keine PRs an Luuke mehr); Ziel ist eine Fassung, die am **PC** gut aussieht und gut fährt.
Hat Luuke etwas selbst geändert oder weggelassen, gilt in der Testfassung die Fork-Lösung.

Stand: 25.11.2026 (auf Luukes 1.6.84). Garagen-Menü (Garage: links „Virtuell fahren“, rechts die Einstellungen; Kachel „Virtuell fahren“ im FAHREN-Menü) ist Luukes allgemeiner Garagen-Code (90-ghosts.js, 51-konsole.js) und bleibt von ihm. Ältere Fassungen: Zweige `sicherung-testversion-1.6.22`, `sicherung-testversion-1.4.67`.

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
  Seit 1.6.60 hat Luuke Startampel (`src/74c-startampel.js`, Optionen → Zusatz-Hardware → Startampel), Startansage und
  Akku kritisch selbst übernommen. Der Zweig `startampel` baut seit 25.11. auf seiner Fassung auf und ergänzt nur, was er
  weggelassen hat: Kennung `AMPEL_STAND`, „Frühstart bricht den Start ab“, „Wartezeit nach dem Start“. `akku-kritisch`
  ist damit gleich Luukes Stand.
- **Schnittstellen zu Luukes 1.6.84 (25.11.):** Luukes FAHREN-Seite hat den Umschalter Echt | Virtuell, seine Garage
  ruft `vfGarageZeigen`, die Optionen-Kacheln „Virtuell“/„RC Heli“ rufen `vfOptionenSeite`. Dafür stehen in unserer
  60d kleine Hilfsfunktionen (`vfAutoListe`, `vfAutoName`, `vfVorschauUrl`, `vfStreckeName`, `vfGarageZeigen`,
  `vfOptionenSeite`): Garage öffnet unsere Garage mit „Virtuell fahren“ rechts, die Optionen-Kacheln verweisen dorthin.
  Luukes AR (`60e-ar.js`, `60f-ar-marker.js`), RC Heli, Neigen-Lenkung, Drift-Physik, Reifenwahl, virtuelle Zeiten
  in Challenges/online und seine virtuelle Garage gehören zu SEINEM VF und sind bei uns nicht angeschlossen.
  Luukes Autos haben seit 1.6.84 `vorschau.png` statt `vorschau.jpg`; die Garage nimmt dann das PNG.

## Liste (jede Zeile wird vor dem Hochladen mit `git grep -F` geprüft)

| Erweiterung | Wo | Prüfung (muss gefunden werden) |
|---|---|---|
| Unser virtuelles Fahren (ganze Datei) | `src/60d-virtuell.js`, `hilfe/virtuelles-fahren.html` | `vf-laden-fork`, `const VF_COCKPIT_FOVH` |
| Startampel am Tisch (seit 1.6.84 auf Luukes Seite Optionen → Zusatz-Hardware → Startampel, BLE) mit Wartezeit und Frühstart-Abbruch | `src/74c-startampel.js`, `src/70-race.js`, `src/00-index.head.html` (#sub-opt-addon) | `AMPEL_STAND`, `id="race-start-warte"`, `function ampelStartVerzoegert` |
| Startansage „Gentlemen, start your engines“ | `src/80-sound.js`, Schalter `setting-announce-start` | `setting-announce-start` |
| Akku kritisch (6 %, „Session abbrechen, Box anfahren!“) | `src/80-sound.js`, Schalter `setting-announce-battery-crit` | `setting-announce-battery-crit`, `AKKU_KRITISCH` |
| ansageAn mit `start: true` und `batterycrit: true` (seit 1.6.60 bei Luuke) | `src/80-sound.js` | `start: true,`, `batterycrit: true };` |
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
| Knopfleiste als Piktogramme wie bei Luuke (23.11., ohne Wetter-Knopf, mit Pad-Diagnose; Ausblenden nach 4 s bleibt) | `src/60d-virtuell.js` (VF_IKONEN, vfKnopfLeisteHtml, vfLeisteUmschalten), Selbsttest am Ende von 95 | `function vfKnopfLeisteHtml`, `vfLeisteUmschalten();`, `Knopfleiste als Piktogramme, ein Knopf blendet` |
| Jede neue virtuelle Fahrt mit Startfüllung (Renneinstellung „Tank beim Start“, ab Werk voll; 23.11.) | `src/60d-virtuell.js` (vfTankFuellen in virtuellStarten), Selbsttest in 95 | `function vfTankFuellen`, `jede neue Fahrt startet mit der Startfuellung` |
| Ausstieg aus der virtuellen Fahrt mit Grund („Fahrt beendet: …“, letzte 10 in `omegasim-vf-ende`); Zurück-Taste während der Fahrt gesperrt (23.11.) | `src/60d-virtuell.js` (virtuellBeenden(grund)), `src/51-konsole.js` (omegaZurueck, Options/Escape), `src/90-ghosts.js` (vfOptionsBelegung), `src/72-challenges.js`, `src/98f-studie.js`, `src/98h-pause.js` | `const VF_ENDE_STORE`, `Zurück ist während der Fahrt gesperrt`, `window.vfOptionsBelegung = bindingDescription` |
| Lebenszeichen der virtuellen Fahrt: erkennt Neuladen der Seite mitten in der Fahrt, meldet „Letzte Fahrt unerwartet abgebrochen“ (23.11.) | `src/60d-virtuell.js` | `const VF_LAEUFT_STORE`, `function vfAbbruchPruefen` |
| Rennende: Ergebnistafel bleibt stehen („Zurück zur Garage“, A/Enter); Garage zeigt Rennmodus und Länge (23.11.) | `src/60d-virtuell.js` | `function vfErgebnisTafel`, `function vfModusText` |
| Startaufstellung freier Strecken (`gitter` in der Strecken-JSON, Heckenhoim V3): Klammern gezeichnet, Spieler auf der Pole, NPCs auf den Plätzen dahinter (25.11.) | `src/60d-virtuell.js`, `tools/strecken/heckenhoim_bau.py`, `img/strecken/heckenhoim.json` | `function vfGitterPlatz`, `"gitter"` |
| Bahnbreite je freier Strecke (`halb` in der Strecken-JSON, `vfHalbW()` statt TRACK_HALF_W im VF); Heckenhoim in echten Maßen (0,093 Einheiten/mm wie die Törnerschleife), ohne hellen Streifen an der Boxengasse (25.11.) | `src/60d-virtuell.js`, `tools/strecken/heckenhoim_bau.py`, `img/strecken/heckenhoim.json` | `function vfHalbW`, `steg.zeichnen` |
| Bulli: Scheiben von innen fast klar (Onboard-Kamera) | `src/60d-virtuell.js` | `innen ? 0.12 : 0.86` |
| Innenspiegel, Außenspiegel (Spider), Armaturenbrett-Cockpit wie im Fork | `src/60d-virtuell.js` | `function vfInnenspiegelMalen`, `function vfCockpit(` |
| Umgebungston (Ambience) ab Werk aus | `src/80-sound.js`, `id="amb-enable"` ohne checked | `let ambienceEnabled = false` |
| Freigaben-Liste „Eigene Autos von Gnen54 und die Freigaben“ | `src/00-index.head.html` (Credits) | `Eigene Autos von Gnen54 und die Freigaben` |
| Testfassung holt Seite/HTML/JSON mit no-cache | `tools/sw.js.in` | `cache: 'no-cache'` |
| Vorschaubilder mit echter 3D-Grafik (WebGL) | `img/autos/{caravelle,spider,gt3,manta,kaefer}/vorschau.jpg`, Werkzeug `tools/vorschau_webgl/` | `function zeichne(auto)` — neue oder geänderte Modelle damit neu zeichnen (`python3 -m http.server 8790` im Repo, dann `node tools/vorschau_webgl/erzeugen.js <autos>`), NICHT mit `tools/vorschau_bilder.py` (fleckig) |
| Selbsttests Fork | `src/95-selftest.js` (Ende) | `Fork gnen54: Selbsttests des virtuellen Fahrens`, `Performance laedt die leichte Fassung` |
| Übersetzungen (EN/ES) aller Fork-Texte | `src/10-ble-explorer.js` | `Stein grau marmoriert`, `Opel Manta B400 (Gnen54, WIP)` |

Nicht mehr in der Testfassung: Ruckel-Testseiten u1-u5.html.
