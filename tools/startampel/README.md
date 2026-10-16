# Startampel für OmegaSim (Raspberry Pi 3)

Eine echte Startampel am Tisch, die OmegaSim per **Bluetooth Low Energy** steuert.
Drei LED-Reihen: oben **Rot**, in der Mitte **Gelb**, unten **Grün** mit 5 Spalten.

## Ablauf

| In OmegaSim                                   | Befehl         | Ampel                                    |
|-----------------------------------------------|----------------|------------------------------------------|
| nichts freigegeben, Rennende, Abbruch         | `ROT`          | Rot                                      |
| Start im Fenster *Bringe die Autos in Position* | `START`      | Rot aus, Gelb an                         |
| Ampelton 1, 2, 3 des Countdowns               | `GRUEN 2/3/5`  | 2, 3, dann alle 5 grünen Spalten (+ Gelb) |
| Grün / Start (auch freies Training)           | `LOS`          | alles aus                                |
| Frühstart im Countdown *                      | `FRUEHSTART`   | Grün aus, Gelb blinkt bis zum Neustart   |
| Gelbe Flagge                                  | `GELB`         | Gelb an                                  |
| Gelbe Flagge aufgehoben (nach der Anfahr-Ampel) | `GELB_AUS`   | Gelb aus                                 |

\* Nur wenn in den Renneinstellungen „Startampel: Frühstart bricht den Start ab“ an ist
(ab Werk an), nicht im WLAN-Mehrspieler und nicht in Challenges. Dann hält OmegaSim den
Countdown an, und „Rennen starten“ beginnt die Abfolge neu. Ist der Schalter aus, läuft
die Ampel weiter und es gilt die normale Frühstart-Strafe.

Der Countdown in OmegaSim hat drei Töne. Wie bei der Ampel-Brücke im Cockpit leuchtet je
Ton ein anteiliger Teil der fünf Spalten (2, 3, 5), damit Lampen und Töne zusammenpassen.

Verliert der Pi die Verbindung zur App, geht die Ampel zur Sicherheit auf Rot
(`BEI_VERBINDUNGSABBRUCH_ROT`).

## Schnittstelle

Der Pi wirbt als BLE-Gerät **„Ampel“** mit einem eigenen GATT-Dienst. Absichtlich nicht der
Nordic-UART-Dienst der Autos – sonst stünde die Ampel im Auto-Verbinden-Dialog.

| | UUID |
|---|---|
| Dienst | `b5a30001-0e9a-4b7c-8d2f-a3f1c0de5a11` |
| Befehle (write, write-without-response) | `b5a30002-0e9a-4b7c-8d2f-a3f1c0de5a11` |

Befehle sind Text, ein Befehl je Schreibvorgang, mit `\n`. Kein Pairing nötig.
In der App: `src/74-startampel.js`.

## Verdrahtung (Vorschlag)

Ein GPIO-Pin liefert nur wenige mA. Jede Reihe/Spalte über einen Treiber schalten, z. B.
einen **ULN2803** (8 Kanäle, reicht für alle 7) oder je einen Logic-Level-MOSFET.

| Kanal          | GPIO (BCM) | Pin am Pi |
|----------------|-----------:|----------:|
| Rot            | 17         | 11        |
| Gelb           | 27         | 13        |
| Grün Spalte 1  | 22         | 15        |
| Grün Spalte 2  | 23         | 16        |
| Grün Spalte 3  | 24         | 18        |
| Grün Spalte 4  | 25         | 22        |
| Grün Spalte 5  | 5          | 29        |

GND vom Pi und vom LED-Netzteil verbinden. Pins und Polarität stehen oben in
`startampel.py` (`PIN_…`, `AKTIV_HIGH`).

## Variante: Raspberry Pi Pico W / Pico WH

Statt eines Raspberry Pi geht auch ein **Pico W oder Pico WH** (mit Bluetooth). Er ist
billiger, braucht keine SD-Karte und ist nach dem Einschalten in einer Sekunde bereit.
Programm: `pico/main.py` (MicroPython), gleicher Bluetooth-Dienst und gleiche Befehle –
die App merkt keinen Unterschied.

Der Pico hat keinen Audioausgang – das macht nichts: die Ansage „Gentlemen, start your
engines“ spricht OmegaSim selbst (siehe unten).

### Verdrahtung Pico

| Kanal          | GPIO | Pin am Pico |
|----------------|-----:|------------:|
| Rot            | GP16 | 21          |
| Gelb           | GP17 | 22          |
| Grün Spalte 1  | GP18 | 24          |
| Grün Spalte 2  | GP19 | 25          |
| Grün Spalte 3  | GP20 | 26          |
| Grün Spalte 4  | GP21 | 27          |
| Grün Spalte 5  | GP22 | 29          |
| GND            |      | 23 (oder ein anderer GND) |

Auch hier jede Reihe/Spalte über einen **ULN2803** (schaltet mit 3,3 V am Eingang sicher)
oder einen Logic-Level-MOSFET – ein Pico-Pin liefert nur wenige mA. Pins und Polarität
stehen oben in `main.py`.

Stromversorgung: über USB (5 V Netzteil oder Powerbank). Die LED-Reihen bekommen ihre
eigene Spannung über den Treiber; GND von Pico und LED-Netzteil verbinden.

### Einrichtung Pico

1. **MicroPython für den Pico W** aufspielen (micropython.org → „Raspberry Pi Pico W“, die
   `.uf2`-Datei, Version 1.22 oder neuer): BOOTSEL-Taste halten, Pico per USB anstecken,
   die Datei auf das Laufwerk „RPI-RP2“ ziehen.
2. **Thonny** öffnen (Interpreter: „MicroPython (Raspberry Pi Pico)“), `pico/main.py`
   öffnen und **als `main.py` auf dem Pico speichern** („Raspberry Pi Pico“ als Ziel).
3. Pico neu starten. Die **Onboard-LED blinkt**, solange er auf OmegaSim wartet, und
   **leuchtet**, sobald die App verbunden ist. Die rote Reihe geht an.
4. In OmegaSim: **Renneinstellungen → Startampel → Verbinden** und „Ampel“ wählen.

Zum Testen ohne App in Thonny im Kommandofenster (Programm vorher mit Strg+C anhalten):

```python
from main import Ampel
a = Ampel()
a.befehl("START"); a.befehl("GRUEN 5"); a.befehl("TEST")
```

## Einrichtung auf dem Pi

Raspberry Pi OS (Bookworm oder neuer). Keine pip-Pakete nötig.

```bash
sudo apt update
sudo apt install -y python3-gpiozero python3-dbus python3-gi bluez
sudo rfkill unblock bluetooth
mkdir -p ~/startampel && cp startampel.py ~/startampel/
sudo python3 ~/startampel/startampel.py
```

Die Ausgabe zeigt „Sichtbar als "Ampel"“. Dann in OmegaSim: **Renneinstellungen →
Startampel (Raspberry Pi) → Verbinden** und „Ampel“ wählen. Geht in Chrome/Edge (PC,
Android) und in der OmegaSim-Android-App, nicht in Firefox oder Safari.

### Autostart

```bash
sudo cp startampel.service /etc/systemd/system/
sudo systemctl enable --now startampel
journalctl -u startampel -f      # Log ansehen
```

Der Dienst läuft als root (Bluetooth-Anmeldung bei BlueZ und GPIO). Pfad in
`startampel.service` anpassen, falls der Ordner woanders liegt.

## Testen ohne App oder ohne LEDs

```bash
python3 startampel.py --sim --stdin   # ohne LEDs, Befehle eintippen
python3 startampel.py --stdin         # echte LEDs, Befehle eintippen (TEST = Lampentest)
python3 startampel.py --tcp 5000      # Befehle übers Netzwerk, z. B. nc <pi> 5000
```

## Ansage „Gentlemen, start your engines“

Die Ansage kommt **von OmegaSim**, nicht von der Ampel – und **nur beim Start-Knopf im
Fenster „Bringe die Autos in Position“** (Tippen oder Controller-Taste X), wenn gerade nichts
läuft (Ton → **Startansage**, ab Werk an). Im selben Moment geht die Ampel auf Gelb. Das
Öffnen des Fensters („Rennen starten“, Cockpit-Knopf, Challenge) löst noch nichts aus; der
Mehrspieler-Countdown schaltet Gelb ohne Ansage. So klingt sie aus dem Tablet, egal ob Pi oder
Pico, und funktioniert auch ganz ohne Ampel.

Soll sie stattdessen vom Pi kommen (z. B. über einen Lautsprecher an der Ampel): in
`startampel.py` `ANSAGE_AN = True` setzen, `sudo apt install espeak-ng` (oder eine eigene
`ansage.wav` neben das Skript legen) – und in OmegaSim die Startansage ausschalten, sonst
kommt sie doppelt.
