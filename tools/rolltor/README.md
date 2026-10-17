# Rolltor-Steuerung (Raspberry Pi Pico W / WH)

Zwei Modell-Rolltore mit je einem Schrittmotor **28BYJ-48 (5 V)** an einem **ULN2803**,
gesteuert von einem **Pico W/WH**:

- **Kalibrieren im Tippbetrieb:** Knopf halten = Tor fährt, loslassen = steht. Dann die
  Endlagen „Zu“ und „Auf“ speichern.
- **Feste Endlagen:** Danach fährt jedes Tor auf Knopfdruck genau in seine Endlage.
- **Bedienung im Browser:** **http://rolltor.local** im Heim-WLAN.
- **Siri:** Kurzbefehle rufen Adressen wie `http://rolltor.local/tor/1/auf` auf.

Im Stillstand sind die Spulen **stromlos**. Das Getriebe des 28BYJ-48 hält das Tor selbst,
nichts wird warm.

## Teile

- Raspberry Pi Pico W oder WH
- 2 × Schrittmotor 28BYJ-48 (5 V)
- 1 × ULN2803 (8 Kanäle, reicht für beide Motoren)
- Netzteil **5 V, mindestens 1 A** für die Motoren (beide zusammen ca. 0,5 A beim Fahren)

## Verdrahtung

| Motor | Ader | ULN2803 Ausgang (Pin) | ULN2803 Eingang (Pin) | Pico GPIO (Pin) |
|-------|------|----------------------:|----------------------:|----------------:|
| Tor 1 | blau   | 1C (18) | 1B (1) | GP2 (4)  |
| Tor 1 | rosa   | 2C (17) | 2B (2) | GP3 (5)  |
| Tor 1 | gelb   | 3C (16) | 3B (3) | GP4 (6)  |
| Tor 1 | orange | 4C (15) | 4B (4) | GP5 (7)  |
| Tor 2 | blau   | 5C (14) | 5B (5) | GP6 (9)  |
| Tor 2 | rosa   | 6C (13) | 6B (6) | GP7 (10) |
| Tor 2 | gelb   | 7C (12) | 7B (7) | GP8 (11) |
| Tor 2 | orange | 8C (11) | 8B (8) | GP9 (12) |

- **Rot** (Mitte) beider Motoren an **+5 V** des Netzteils.
- ULN2803 **Pin 9 (GND)** an GND des Netzteils **und** an GND des Pico (z. B. Pin 3 oder 8).
- ULN2803 **Pin 10 (COM)** an **+5 V**. Das sind die Freilaufdioden, bitte nicht weglassen.
- Den Pico per USB versorgen oder aus demselben 5-V-Netzteil über **VSYS (Pin 39)**. Soll
  dabei zeitweise auch USB stecken (z. B. für Thonny), eine Schottky-Diode (z. B. 1N5817)
  in die Leitung zu VSYS setzen, damit das Netzteil nicht in den Computer zurückspeist.

Läuft ein Tor bei „Auf“ nach unten, einfach auf der Seite **Richtung umkehren** drücken
(oder in `main.py` `"umkehren": True`). Ruckelt ein Motor nur hin und her, sind zwei Adern
vertauscht. Die Reihenfolge blau, rosa, gelb, orange ist die übliche.

## Einrichtung

1. **MicroPython für den Pico W** aufspielen (micropython.org → „Raspberry Pi Pico W“,
   `.uf2`, Version 1.22 oder neuer): BOOTSEL halten, Pico anstecken, Datei auf „RPI-RP2“ ziehen.
2. In `main.py` oben das **Heim-WLAN** eintragen:
   ```python
   HEIM_WLAN_NAME = "MeinWLAN"
   HEIM_WLAN_PASSWORT = "geheim"
   ```
3. Mit **Thonny** beide Dateien auf den Pico speichern: `main.py` und `seite.html`.
4. Pico neu starten. Die **Onboard-LED leuchtet**, wenn das Heim-WLAN verbunden ist. In
   Thonny steht die Adresse, z. B. `http://rolltor.local oder http://192.168.178.57`.
5. Im Browser **http://rolltor.local** öffnen. Klappt `.local` nicht (manche
   Android-Geräte), die Zahlen-Adresse nehmen.

Ist das Heim-WLAN nicht erreichbar, macht der Pico nach 20 s ein **eigenes WLAN
„Rolltore“** auf (Passwort `rolltore`, LED blinkt). Dann geht die Bedienung über
http://192.168.4.1, Siri aber nicht.

## Kalibrieren

Bei jedem Tor auf **Kalibrieren** tippen:

1. Mit **▼ halten** bzw. **▲ halten** das Tor ganz **schließen**. Feinarbeit mit **▼ fein / ▲ fein**
   (je ein kleiner Schritt, etwa 0,25 mm bei 10 mm Wickelwelle).
2. **Zu speichern.**
3. Das Tor ganz **öffnen** (ca. 50 mm Fahrweg).
4. **Auf speichern.**

Danach sind **Auf** und **Zu** frei, und der Balken zeigt, wie weit das Tor offen ist.

Ohne Endschalter zählt der Pico die Schritte und speichert die Position nach jeder Fahrt.
**Fällt der Strom während einer Fahrt aus**, weiß er beim Neustart nicht genau, wo das Tor
steht. Dann zeigt die Seite „Position unsicher“ und sperrt Auf/Zu, bis du das Tor (per
Tippen oder von Hand) auf eine Endlage gebracht und **„Tor steht auf Zu“** bzw. **„Tor
steht auf Auf“** gedrückt hast.

## Siri (iPhone, Kurzbefehle-App)

Das iPhone muss im selben WLAN sein wie der Pico.

1. **Kurzbefehle**-App → **+** (neuer Kurzbefehl).
2. Aktion **„Inhalte von URL abrufen“** hinzufügen, als URL eintragen:
   `http://rolltor.local/tor/1/auf`
3. Optional Aktion **„Text sprechen“** dahinter: Der Pico antwortet z. B. „Tor 1 fährt auf.“
   oder „Tor 1 ist schon offen.“
4. Den Kurzbefehl so **benennen**, wie du ihn sagen willst, z. B. **„Rolltor eins auf“**.
5. „**Hey Siri, Rolltor eins auf**“.

Alle Adressen:

| Adresse | Wirkung |
|---|---|
| `/tor/1/auf`, `/tor/2/auf` | öffnen |
| `/tor/1/zu`, `/tor/2/zu` | schließen |
| `/tor/1/stopp` | anhalten |
| `/tor/1/umschalten` | offen ↔ zu |
| `/tor/alle/auf`, `/tor/alle/zu`, `/tor/alle/stopp` | beide Tore |

Ist in `main.py` eine `WEB_PIN` gesetzt, hinten `?pin=1234` anhängen.

## Einstellungen (oben in `main.py`)

| Wert | Bedeutung |
|---|---|
| `TAKTE_FAHRT = 2` | Tempo: 2 ms je Halbschritt ≈ 7 U/min. 50 mm bei 10 mm Wickelwelle ≈ 13 s. Kleiner = schneller (1 ist die Grenze des Motors). |
| `TAKTE_TIPPEN = 3` | Tempo im Tippbetrieb |
| `TAKTE_ANLAUF`, `ANLAUF_SCHRITTE` | sanfter Anlauf am Beginn jeder Fahrt |
| `FEINSCHRITT = 32` | Halbschritte je „fein“-Druck |
| `TORE` | Namen, Pins und Drehrichtung der Tore |
| `WEB_PIN` | optionale PIN für Seite und Siri-Adressen |

Die gespeicherten Positionen liegen auf dem Pico in `tore.json`.
