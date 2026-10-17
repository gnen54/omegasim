# Startampel für OmegaSim (Raspberry Pi 3)

Eine echte Startampel am Tisch, die OmegaSim per **Bluetooth Low Energy** steuert.
Drei LED-Reihen: oben **Rot**, in der Mitte **Gelb**, unten **Grün** mit 5 Spalten.

## Ablauf

| In OmegaSim                                   | Befehl         | Ampel                                    |
|-----------------------------------------------|----------------|------------------------------------------|
| nichts freigegeben, Rennende, Abbruch         | `ROT`          | Rot                                      |
| Start im Fenster *Bringe die Autos in Position* | `START`      | Rot aus, Gelb an                         |
| Ampelton 1 bis 5 des Countdowns (1 s Takt)   | `GRUEN 1…5`    | 1, 2, 3, 4, dann alle 5 grünen Spalten (+ Gelb) |
| Grün / Start (auch freies Training)           | `LOS`          | alles aus                                |
| Frühstart im Countdown *                      | `FRUEHSTART`   | Grün aus, Gelb blinkt bis zum Neustart   |
| Gelbe Flagge                                  | `GELB`         | Gelb an                                  |
| Gelbe Flagge aufgehoben (nach der Anfahr-Ampel) | `GELB_AUS`   | Gelb aus                                 |

\* Nur wenn in den Renneinstellungen „Startampel: Frühstart bricht den Start ab“ an ist
(ab Werk an), nicht im WLAN-Mehrspieler und nicht in Challenges. Dann hält OmegaSim den
Countdown an, und „Rennen starten“ beginnt die Abfolge neu. Ist der Schalter aus, läuft
die Ampel weiter und es gilt die normale Frühstart-Strafe.

Nach dem Start im Fenster steht die Ampel eine **Wartezeit** lang auf Gelb (mit der
Ansage), erst dann beginnt die grüne Sequenz – Renneinstellungen → **Wartezeit nach dem
Start**, ab Werk 4 s, 0 = sofort. Der Start-Knopf im Cockpit bricht das Warten ab (Rot).

Der Countdown in OmegaSim hat fünf Töne im Sekundentakt, wie an einer echten Startampel: je
Ton leuchtet eine grüne Spalte mehr, nach dem fünften kommt Grün (alles aus). Die Ampel-Brücke
im Cockpit zeigt dasselbe.

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

## Betrieb ohne OmegaSim: Steckverbinder und Steuerseite (nur Raspberry Pi)

Ohne OmegaSim kann die Ampel ihre **eigene Startsequenz** fahren (Befehl `SEQUENZ`): Gelb,
Wartezeit (ab Werk 4 s), fünf grüne Spalten im Sekundentakt, dann alles aus. Auslösen lässt
sie sich über den Steckverbinder, die Steuerseite im Browser oder einen Befehl auf dem Pi.

**Vorrang:** Ist OmegaSim verbunden, steuert die App. Steckverbinder und Steuerseite können
dann nur noch **Rot / Stopp** auslösen (`OMEGASIM_VORRANG`). Ein Befehl von OmegaSim bricht
eine laufende eigene Sequenz ab.

### Steuerseite im Browser

Läuft das Programm, zeigt der Pi im WLAN eine Steuerseite:

**http://raspberrypi.local:8080** (oder `http://<IP-des-Pi>:8080`; die IP zeigt `hostname -I`)

Sie zeigt die Ampel live und hat Knöpfe für Startsequenz, Gelbphase, Frühstart, Lampentest,
„Alles aus“ und Rot / Stopp, dazu den Regler für die Wartezeit (wird gespeichert). Das Handy
muss im selben WLAN sein wie der Pi.

Ohne Weiteres kann **jeder im WLAN** die Seite bedienen. Wer das nicht will, setzt oben in
`startampel.py` eine Zahl als `WEB_PIN`; die Seite fragt dann einmal danach.

### Steckverbinder mit Optokopplern

Vier Eingänge, jeder über einen Optokoppler (z. B. **PC817**), damit fremde Spannungen nie
an den Pi kommen – die GPIO-Pins vertragen nur 3,3 V.

| Eingang     | Befehl        | Art                                  | GPIO | Pin am Pi |
|-------------|---------------|--------------------------------------|-----:|----------:|
| Start       | `SEQUENZ`     | beim Einschalten des Signals         | 6    | 31        |
| Gelb        | `GELB`        | solange das Signal anliegt           | 13   | 33        |
| Rot / Stopp | `ROT`         | beim Einschalten des Signals         | 19   | 35        |
| Frühstart   | `FRUEHSTART`  | beim Einschalten des Signals         | 26   | 37        |
| GND         |               |                                      |      | 39        |

Schaltung je Eingang:

```
 Signal + ──[ R ]──┬──► PC817 Pin 1 (Anode)        PC817 Pin 4 (Kollektor) ──► GPIO (z. B. 6)
                   │                               PC817 Pin 3 (Emitter)   ──► GND am Pi (Pin 39)
 Signal − ─────────┴──► PC817 Pin 2 (Kathode)
         (1N4148 antiparallel zu Pin 1/2 als Verpolschutz)
```

Vorwiderstand R je nach Signalspannung: **5 V → 330–470 Ω**, **12 V → 1,2–2,2 kΩ**,
**24 V → 2,2–4,7 kΩ**. Einen Pull-up braucht es nicht, das Programm schaltet den internen ein.
Liegt das Signal an, leuchtet die LED im Optokoppler, und der Pin geht auf GND – das Programm
wertet das als „aktiv“ (`EINGANG_AKTIV_LOW = True`).

Die Zuordnung steht oben in `startampel.py` in der Tabelle `EINGAENGE` und lässt sich ändern,
z. B. ein Eingang weniger oder `LOS` statt `SEQUENZ`.

Ohne Hardware testen: `python3 startampel.py --sim --stdin` und dann `PIN 6 1` / `PIN 6 0`
eintippen.

### Per App (z. B. RaspController)

Statt GPIO-Pins direkt zu schalten (das liefe am Programm vorbei), schickt man einen Befehl
an das laufende Programm. In RaspController als eigenen Befehl („Custom command“) anlegen:

```bash
python3 /home/pi/startampel/startampel.py --befehl SEQUENZ
```

Genauso `ROT`, `GELB`, `GELB_AUS`, `FRUEHSTART`, `TEST`. Der Befehlsport (5000) ist nur auf
dem Pi selbst erreichbar (`TCP_ADRESSE = "127.0.0.1"`).

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

### Wenn das Tablet eine Kopplungsanfrage zeigt und der Pi gleich wieder trennt

Der Pi 3 kann auch klassisches Bluetooth, und Android versucht dann, ihn klassisch zu
koppeln. Das Programm fängt das ab: es schaltet den Pi beim Start auf **reines Bluetooth LE**
(`NUR_LE = True`) und beantwortet Kopplungsanfragen selbst, ohne PIN. Im Terminal steht dann
„Bluetooth: nur LE“ und „Kopplungsagent aktiv“. Falls es trotzdem trennt:

1. Am Tablet unter **Einstellungen → Bluetooth** einen alten Eintrag „Ampel“ oder
   „raspberrypi“ **entkoppeln** (von einem früheren Versuch).
2. Am Pi Bluetooth neu starten: `sudo systemctl restart bluetooth`, dann das Programm neu.
3. Steht im Terminal „btmgmt fehlt“: in `/etc/bluetooth/main.conf` unter `[General]` die
   Zeile `ControllerMode = le` eintragen und `sudo systemctl restart bluetooth`.
4. In Chrome neu verbinden (Renneinstellungen → Startampel → Verbinden). Eine
   Kopplungsanfrage darf man bestätigen – sie geht jetzt durch.

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
