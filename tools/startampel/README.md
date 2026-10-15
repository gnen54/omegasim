# Startampel für OmegaSim (Raspberry Pi 3)

Eine echte Startampel am Tisch, die OmegaSim per **Bluetooth Low Energy** steuert.
Drei LED-Reihen: oben **Rot**, in der Mitte **Gelb**, unten **Grün** mit 5 Spalten.

## Ablauf

| In OmegaSim                                   | Befehl         | Ampel                                    |
|-----------------------------------------------|----------------|------------------------------------------|
| nichts freigegeben, Rennende, Abbruch         | `ROT`          | Rot                                      |
| „Rennen starten“ (Fenster *Autos in Position*) | `START`        | Rot aus, Gelb an, Ansage                 |
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

## Einrichtung auf dem Pi

Raspberry Pi OS (Bookworm oder neuer). Keine pip-Pakete nötig.

```bash
sudo apt update
sudo apt install -y python3-gpiozero python3-dbus python3-gi bluez espeak-ng
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

## Eigene Ansage

Eine Datei `ansage.wav` neben `startampel.py` legen; sie wird bei `START` mit `aplay`
abgespielt. Ohne Datei spricht `espeak-ng` den Text aus `ANSAGE_TEXT`.
