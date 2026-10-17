#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Startampel fuer OmegaSim - Raspberry Pi 3, Bluetooth Low Energy.

Gegenpart in der App: src/74-startampel.js (Renneinstellungen -> "Startampel (Raspberry Pi)").

Aufbau der Ampel
    Oben    : rote Reihe   (1 Kanal)
    Mitte   : gelbe Reihe  (1 Kanal)
    Unten   : gruene Reihe (5 Spalten, 5 Kanaele)

Ablauf (Befehle kommen von OmegaSim)
    ROT          Gesperrt: Rot an. Auch bei Rennende und Abbruch.
    START        Start im Fenster "Bringe die Autos in Position": Rot aus, Gelb an. (Die Ansage "Gentlemen,
                 start your engines" kommt von OmegaSim; siehe ANSAGE_AN.)
    GRUEN <n>    Ampelton des Countdowns: n gruene Spalten leuchten (die App schickt 1 bis 5).
    LOS          Gruen/Start: alle LEDs aus, das Rennen laeuft.
    FRUEHSTART   Fruehstart im Countdown: Gruen aus, Gelb blinkt, bis START kommt.
    GELB         Gelbe Flagge im Rennen: Gelb an ...
    GELB_AUS     ... bis sie aufgehoben ist.

Schnittstelle
    Der Pi ist ein BLE-Peripheriegeraet mit einem eigenen GATT-Dienst. OmegaSim schreibt die
    Befehle als Text (mit "\\n") auf die Befehls-Characteristic. Kein Pairing noetig.
    Umgesetzt direkt ueber BlueZ/D-Bus - auf dem Pi keine pip-Pakete noetig.

Start
    sudo python3 startampel.py            # Bluetooth LE, echte LEDs, Eingaenge, Netzwerk-Befehle
    python3 startampel.py --befehl SEQUENZ   # Befehl an das laufende Programm (RaspController)
    Steuerseite im Browser: http://raspberrypi.local:8080
    python3 startampel.py --sim --stdin   # ohne Hardware, Befehle eintippen
    python3 startampel.py --tcp 5000      # Befehle uebers Netzwerk (Test)
"""

import argparse
import os
import queue
import re
import shutil
import socket
import subprocess
import sys
import threading
import time

# ============================================================================
# KONFIGURATION
# ============================================================================

# GPIO-Pins (BCM-Nummerierung). Jeder Pin schaltet ueber einen Treiber
# (z. B. ULN2803 oder MOSFET) eine komplette Reihe bzw. Spalte.
PIN_ROT = 17
PIN_GELB = 27
PINS_GRUEN = [22, 23, 24, 25, 5]      # Spalte 1 .. 5, von links nach rechts

AKTIV_HIGH = True        # False, falls der Treiber bei LOW einschaltet
BLINK_TAKT_S = 0.5       # Halbperiode beim Blinken (an/aus je 0,5 s)

# Soll Gelb waehrend der Gruenphase weiterleuchten?
GELB_WAEHREND_GRUEN = True

# Ansage beim Start - AB WERK AUS: "Gentlemen, start your engines" spricht OmegaSim selbst
# (Ton -> Startansage). Nur einschalten, wenn die Ansage vom Pi kommen soll, und dann in
# OmegaSim die Startansage ausschalten, sonst kommt sie doppelt.
# ANSAGE_DATEI (WAV, im Ordner des Skripts) wird mit aplay abgespielt; gibt es sie nicht,
# spricht espeak-ng ANSAGE_TEXT.
ANSAGE_AN = False
ANSAGE_DATEI = "ansage.wav"
ANSAGE_TEXT = "Gentlemen, start your engines"

# Bluetooth LE - die UUIDs muessen zu src/74-startampel.js passen.
BLE_NAME = "Ampel"   # kurz halten: Name + Dienst-UUID muessen in 31 Byte Werbung passen
AMPEL_SERVICE = "b5a30001-0e9a-4b7c-8d2f-a3f1c0de5a11"
AMPEL_BEFEHL = "b5a30002-0e9a-4b7c-8d2f-a3f1c0de5a11"
BEI_VERBINDUNGSABBRUCH_ROT = True   # Sicherheit: App weg -> Rot
# NUR BLUETOOTH LE: der Pi 3 kann auch klassisches Bluetooth, und dann versucht Android, ihn
# klassisch zu koppeln (Kopplungsanfrage am Tablet, danach trennt BlueZ). Mit True schaltet
# das Programm den Pi beim Start auf reines LE (btmgmt bredr off). Klassisches Bluetooth
# (Tastatur, Lautsprecher am Pi) geht dann nicht - fuer eine Ampel egal. False = aus.
NUR_LE = True

# ---- EIGENE STARTSEQUENZ (ohne OmegaSim) ----
# Befehl SEQUENZ (Eingang "Start", --befehl, Netzwerk): Gelb, Wartezeit, fuenf gruene Spalten
# im Takt, dann alles aus - wie in OmegaSim. Abbruch durch ROT, FRUEHSTART oder einen Befehl
# von OmegaSim.
SEQUENZ_WARTE_S = 4      # Gelb vor dem ersten gruenen Licht
SEQUENZ_TAKT_S = 1.0     # Abstand der gruenen Lichter

# ---- EXTERNE EINGAENGE (ueber Optokoppler) ----
# Jeder Eingang: (GPIO, Befehl, Art).
#   "puls"  = einmal beim Einschalten des Signals
#   "dauer" = solange das Signal anliegt; beim Abschalten der Gegenbefehl (GELB -> GELB_AUS)
# Freie Pins neben den LED-Pins: GPIO 6, 13, 19, 26 (Pins 31, 33, 35, 37; GND an Pin 39).
EINGAENGE_AN = True
EINGAENGE = [
    (6, "SEQUENZ", "puls"),       # Start: eigene Startsequenz
    (13, "GELB", "dauer"),        # Gelbphase, solange das Signal anliegt
    (19, "ROT", "puls"),          # Rennende / Abbruch / Not-Aus
    (26, "FRUEHSTART", "puls"),   # Fruehstart: Gruen aus, Gelb blinkt
]
GEGENBEFEHL = {"GELB": "GELB_AUS"}
# Optokoppler-Ausgang (Transistor) zieht den Pin nach GND: aktiv = LOW, interner Pull-up.
EINGANG_AKTIV_LOW = True
ENTPRELL_S = 0.05
# Ist OmegaSim verbunden, hat die App Vorrang: von aussen wird dann nur ROT angenommen.
OMEGASIM_VORRANG = True

# ---- STEUERSEITE IM BROWSER ----
# Der Pi zeigt im WLAN eine Steuerseite: http://<Name-oder-IP-des-Pi>:8080
# (z. B. http://raspberrypi.local:8080). None = aus. WEB_PIN: optionale Zahl, die man auf der
# Seite einmal eingeben muss - ohne PIN kann jeder im WLAN die Ampel bedienen.
WEB_PORT = 8080
WEB_PIN = None
EINSTELLUNGEN_DATEI = "einstellungen.json"   # merkt sich die Wartezeit von der Steuerseite

# ---- BEFEHLE UEBER DAS NETZWERK (z. B. RaspController) ----
# Das Programm nimmt Befehle auf diesem Port an, nur vom Pi selbst (127.0.0.1). Senden mit:
#     python3 startampel.py --befehl SEQUENZ
# None = aus. "0.0.0.0" bei TCP_ADRESSE oeffnet den Port fuers ganze WLAN (ohne Passwort!).
TCP_PORT = 5000
TCP_ADRESSE = "127.0.0.1"

# Befehle -> Aktion. Links die Texte, die OmegaSim sendet.
BEFEHLE = {
    "ROT": "sperren",
    "START": "vorstart",
    "GRUEN": "gruen_weiter",   # "GRUEN 3" setzt 3 Spalten, "GRUEN" allein eine mehr
    "LOS": "los",
    "FRUEHSTART": "fruehstart",
    "GELB": "gelb_an",
    "GELB_AUS": "gelb_aus",
    "STATUS": "status",
    "TEST": "lampentest",
    "SEQUENZ": "sequenz",      # eigene Startsequenz (ohne OmegaSim)
}
# Diese Befehle lassen eine laufende eigene Startsequenz weiterlaufen; alle anderen brechen
# sie ab (z. B. START/GRUEN von OmegaSim, ROT, FRUEHSTART).
SEQUENZ_LAESST_LAUFEN = ("SEQUENZ", "STATUS", "TEST")

# ============================================================================
# LED-ANSTEUERUNG
# ============================================================================


def log(text):
    print(time.strftime("%H:%M:%S"), text, flush=True)


class SimLeuchte:
    """Ersatz fuer eine LED, wenn keine GPIO-Hardware vorhanden ist."""

    def __init__(self):
        self.is_lit = False

    def on(self):
        self.is_lit = True

    def off(self):
        self.is_lit = False


def erzeuge_leuchten(simulation):
    """Liefert (rot, gelb, [gruen1..5], ist_simulation)."""
    if not simulation:
        try:
            from gpiozero import LED
            rot = LED(PIN_ROT, active_high=AKTIV_HIGH)
            gelb = LED(PIN_GELB, active_high=AKTIV_HIGH)
            gruen = [LED(p, active_high=AKTIV_HIGH) for p in PINS_GRUEN]
            return rot, gelb, gruen, False
        except Exception as fehler:  # kein Pi, gpiozero fehlt, ...
            log(f"GPIO nicht verfuegbar ({fehler}) - nutze Simulation.")
    return SimLeuchte(), SimLeuchte(), [SimLeuchte() for _ in range(5)], True


# ============================================================================
# ZUSTANDSAUTOMAT
# ============================================================================


class Ampel:
    GESPERRT = "gesperrt"
    VORSTART = "vorstart"
    STARTSEQUENZ = "startsequenz"
    RENNEN = "rennen"
    GELBPHASE = "gelbphase"
    FRUEHSTART = "fruehstart"

    def __init__(self, simulation=False):
        self.rot, self.gelb, self.gruen, self.sim = erzeuge_leuchten(simulation)
        self.lock = threading.RLock()
        self.zustand = None
        self.gruen_anzahl = 0
        self._blinken = threading.Event()
        self._stop = threading.Event()
        self._sequenz_nr = 0
        self.sequenz_aktiv = False
        self.omegasim_verbunden = False
        threading.Thread(target=self._blink_schleife, daemon=True).start()
        self.sperren()

    # ---------------------------------------------------------------- Helfer
    def _blink_schleife(self):
        an = False
        while not self._stop.is_set():
            if self._blinken.wait(0.1):
                an = not an
                with self.lock:
                    if self._blinken.is_set():
                        (self.gelb.on if an else self.gelb.off)()
                time.sleep(BLINK_TAKT_S)
            else:
                an = False

    def _setze(self, rot=False, gelb=False, gruen=0, gelb_blinkt=False):
        self._blinken.clear()
        (self.rot.on if rot else self.rot.off)()
        (self.gelb.on if gelb else self.gelb.off)()
        for i, led in enumerate(self.gruen):
            (led.on if i < gruen else led.off)()
        self.gruen_anzahl = gruen
        if gelb_blinkt:
            self._blinken.set()
        self._anzeigen()

    def _anzeigen(self):
        punkt = lambda an: "●" if an else "○"
        gelb = "◐ blinkt" if self._blinken.is_set() else punkt(self.gelb.is_lit)
        gruen = "".join(punkt(l.is_lit) for l in self.gruen)
        log(f"Rot {punkt(self.rot.is_lit)} | Gelb {gelb} | Grün {gruen}   [{self.zustand}]")

    # -------------------------------------------------------------- Aktionen
    def sperren(self, _arg=None):
        with self.lock:
            self.zustand = self.GESPERRT
            self._setze(rot=True)

    def vorstart(self, _arg=None):
        with self.lock:
            self.zustand = self.VORSTART
            self._setze(gelb=True)
        ansage_abspielen()

    def gruen_weiter(self, anzahl=None):
        with self.lock:
            if self.zustand not in (self.VORSTART, self.STARTSEQUENZ):
                log(f"GRUEN ignoriert (Zustand: {self.zustand})")
                return
            neu = self.gruen_anzahl + 1 if anzahl is None else anzahl
            self.zustand = self.STARTSEQUENZ
            self._setze(gelb=GELB_WAEHREND_GRUEN, gruen=max(0, min(5, neu)))

    def los(self, _arg=None):
        # Auch aus "gesperrt": freies Training startet ohne Countdown.
        with self.lock:
            if self.zustand not in (self.GESPERRT, self.VORSTART, self.STARTSEQUENZ):
                log(f"LOS ignoriert (Zustand: {self.zustand})")
                return
            self.zustand = self.RENNEN
            self._setze()

    def fruehstart(self, _arg=None):
        with self.lock:
            if self.zustand not in (self.VORSTART, self.STARTSEQUENZ):
                log(f"FRUEHSTART ignoriert (Zustand: {self.zustand})")
                return
            self.zustand = self.FRUEHSTART
            self._setze(gelb_blinkt=True)

    def gelb_an(self, _arg=None):
        with self.lock:
            if self.zustand not in (self.RENNEN, self.GELBPHASE):
                log(f"GELB ignoriert (Zustand: {self.zustand})")
                return
            self.zustand = self.GELBPHASE
            self._setze(gelb=True)

    def gelb_aus(self, _arg=None):
        with self.lock:
            if self.zustand != self.GELBPHASE:
                log(f"GELB_AUS ignoriert (Zustand: {self.zustand})")
                return
            self.zustand = self.RENNEN
            self._setze()

    def sequenz(self, _arg=None):
        """Eigene Startsequenz in einem eigenen Faden: Gelb, Wartezeit, 1..5 Gruen, LOS."""
        with self.lock:
            if self.zustand not in (self.GESPERRT, self.FRUEHSTART, self.VORSTART):
                log(f"SEQUENZ ignoriert (Zustand: {self.zustand})")
                return
            self._sequenz_nr += 1
            nr = self._sequenz_nr
        threading.Thread(target=self._sequenz_lauf, args=(nr,), daemon=True).start()

    def _sequenz_lauf(self, nr):
        def gilt():
            return nr == self._sequenz_nr and self.zustand in (self.VORSTART, self.STARTSEQUENZ)

        def warte(sekunden):
            ende = time.monotonic() + sekunden
            while time.monotonic() < ende:
                if not gilt():
                    return False
                time.sleep(0.02)
            return gilt()

        log("Eigene Startsequenz.")
        self.sequenz_aktiv = True
        try:
            self._sequenz_schritte(nr, gilt, warte)
        finally:
            if nr == self._sequenz_nr:
                self.sequenz_aktiv = False

    def _sequenz_schritte(self, nr, gilt, warte):
        self.vorstart()
        if not warte(SEQUENZ_WARTE_S):
            return log("Startsequenz abgebrochen.")
        for n in range(1, 6):
            with self.lock:
                if not gilt():
                    return log("Startsequenz abgebrochen.")
                self.gruen_weiter(n)
            if not warte(SEQUENZ_TAKT_S):
                return log("Startsequenz abgebrochen.")
        with self.lock:
            if gilt():
                self.los()

    def sequenz_abbrechen(self):
        self._sequenz_nr += 1
        self.sequenz_aktiv = False

    def zustand_json(self):
        return {"zustand": self.zustand, "rot": bool(self.rot.is_lit),
                "gelb": bool(self.gelb.is_lit), "blinkt": self._blinken.is_set(),
                "gruen": self.gruen_anzahl, "omegasim": self.omegasim_verbunden,
                "sequenz": self.sequenz_aktiv, "warte": SEQUENZ_WARTE_S}

    def status(self, _arg=None):
        self._anzeigen()

    def lampentest(self, _arg=None):
        """Alle LEDs 2 s an, dann zurueck in den vorherigen Zustand."""
        with self.lock:
            vorher = (self.rot.is_lit, self.gelb.is_lit, self.gruen_anzahl, self._blinken.is_set())
            self._setze(rot=True, gelb=True, gruen=5)
            time.sleep(2)
            self._setze(rot=vorher[0], gelb=vorher[1], gruen=vorher[2], gelb_blinkt=vorher[3])

    def beenden(self):
        self._stop.set()
        self._setze()

    # ------------------------------------------------------------- Befehle
    def befehl(self, zeile):
        zeile = zeile.strip().upper()
        if not zeile:
            return
        treffer = re.match(r"^([A-Z_]+)\s*(\d*)$", zeile)
        if not treffer or treffer.group(1) not in BEFEHLE:
            log(f"Unbekannter Befehl: {zeile!r}")
            return
        name, zahl = treffer.group(1), treffer.group(2)
        log(f"Befehl: {zeile}")
        if name not in SEQUENZ_LAESST_LAUFEN:
            self.sequenz_abbrechen()
        getattr(self, BEFEHLE[name])(int(zahl) if zahl else None)


class Befehlsschlange:
    """Arbeitet Befehle in Eingangsreihenfolge in einem eigenen Faden ab, damit der
    Bluetooth-Empfang nie auf die LEDs (oder den Lampentest) warten muss."""

    def __init__(self, ampel):
        self.ampel = ampel
        self.q = queue.Queue()
        self.rest = ""
        threading.Thread(target=self._lauf, daemon=True).start()

    def daten(self, text):
        self.rest += text
        teile = re.split(r"[\r\n;]", self.rest)
        self.rest = teile.pop()
        for zeile in teile:
            self.q.put(zeile)

    def zeile(self, zeile):
        self.q.put(zeile)

    def _lauf(self):
        while True:
            zeile = self.q.get()
            try:
                self.ampel.befehl(zeile)
            finally:
                self.q.task_done()


# ============================================================================
# EXTERNE EINGAENGE (Optokoppler)
# ============================================================================


class Eingaenge:
    """Die Signale am Steckverbinder. Jeder Eingang loest einen Befehl aus (siehe EINGAENGE).
    Ohne GPIO (--sim) lassen sie sich mit "PIN <gpio> 1|0" ueber die Tastatur nachstellen."""

    def __init__(self, ampel, schlange, simulation):
        self.ampel = ampel
        self.schlange = schlange
        self.tasten = []
        self.liste = {gpio: (befehl, art) for gpio, befehl, art in EINGAENGE}
        if not EINGAENGE_AN or not self.liste:
            return
        if simulation:
            log("Eingaenge simuliert: 'PIN <gpio> 1' / 'PIN <gpio> 0'.")
            return
        try:
            from gpiozero import Button
        except Exception as fehler:
            log(f"Eingaenge nicht verfuegbar ({fehler}).")
            return
        for gpio in self.liste:
            taste = Button(gpio, pull_up=EINGANG_AKTIV_LOW, bounce_time=ENTPRELL_S)
            taste.when_pressed = lambda g=gpio: self.signal(g, True)
            taste.when_released = lambda g=gpio: self.signal(g, False)
            self.tasten.append(taste)
        log("Eingaenge aktiv: " + ", ".join(f"GPIO{g}={b}" for g, (b, _a) in self.liste.items()))

    def signal(self, gpio, aktiv):
        if gpio not in self.liste:
            return log(f"GPIO{gpio} ist kein Eingang.")
        befehl, art = self.liste[gpio]
        if not aktiv:
            if art != "dauer" or befehl not in GEGENBEFEHL:
                return
            befehl = GEGENBEFEHL[befehl]
        extern_befehl(self.ampel, self.schlange, befehl, f"Eingang GPIO{gpio}")


def extern_befehl(ampel, schlange, befehl, quelle):
    """Befehl von aussen (Steckverbinder, Steuerseite). Ist OmegaSim verbunden, gilt nur ROT."""
    if OMEGASIM_VORRANG and ampel.omegasim_verbunden and befehl != "ROT":
        log(f"{quelle}: {befehl} ignoriert - OmegaSim ist verbunden.")
        return False
    log(f"{quelle}: {befehl}")
    schlange.zeile(befehl)
    return True


# ============================================================================
# STEUERSEITE IM BROWSER
# ============================================================================

WEB_ERLAUBT = ("SEQUENZ", "ROT", "GELB", "GELB_AUS", "FRUEHSTART", "TEST", "LOS")

STEUERSEITE = """<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Startampel</title>
<style>
  :root { --bg:#111418; --karte:#1b2027; --text:#e8ecf1; --leise:#8b95a3; --rand:#2b323c;
          --rot:#ff3b30; --gelb:#ffcc00; --gruen:#34c759; --aus:#2a2f36; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text);
         font:16px/1.4 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
  main { max-width:520px; margin:0 auto; padding:16px; }
  h1 { font-size:20px; margin:4px 0 2px; }
  .zeile { color:var(--leise); font-size:14px; min-height:20px; }
  .ampel { background:#000; border:1px solid var(--rand); border-radius:14px; padding:14px;
           display:grid; gap:10px; margin:14px 0; }
  .reihe { display:grid; grid-template-columns:repeat(5,1fr); gap:8px; }
  .lampe { aspect-ratio:1; border-radius:50%; background:var(--aus); transition:background .1s, box-shadow .1s; }
  .an.r { background:var(--rot); box-shadow:0 0 14px var(--rot); }
  .an.y { background:var(--gelb); box-shadow:0 0 14px var(--gelb); }
  .an.g { background:var(--gruen); box-shadow:0 0 14px var(--gruen); }
  .hinweis { background:#3a2a00; color:#ffd666; border-radius:10px; padding:10px 12px; font-size:14px; margin-bottom:12px; }
  .knoepfe { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
  button { font:inherit; font-weight:600; color:var(--text); background:var(--karte); border:1px solid var(--rand);
           border-radius:12px; padding:16px 10px; min-height:56px; cursor:pointer; }
  button:active { transform:scale(.98); }
  button:disabled { opacity:.35; cursor:not-allowed; }
  .gross { grid-column:1 / -1; background:#123d1f; border-color:#1f6b35; font-size:18px; }
  .stopp { grid-column:1 / -1; background:#4a1210; border-color:#8a221d; font-size:18px; }
  .karte { background:var(--karte); border:1px solid var(--rand); border-radius:12px; padding:12px 14px; margin-top:14px; }
  .regler { display:flex; align-items:center; gap:12px; }
  input[type=range] { flex:1; accent-color:var(--gruen); }
  .wert { min-width:44px; text-align:right; font-variant-numeric:tabular-nums; }
  .fehler { color:#ff8a80; }
</style></head><body><main>
  <h1>Startampel</h1>
  <div class="zeile" id="zustand">Verbinde …</div>
  <div class="ampel" aria-label="Ampel">
    <div class="reihe" id="r-rot"></div><div class="reihe" id="r-gelb"></div><div class="reihe" id="r-gruen"></div>
  </div>
  <div class="hinweis" id="hinweis" hidden>OmegaSim ist verbunden – die App steuert die Ampel. Hier geht nur Rot / Stopp.</div>
  <div class="knoepfe">
    <button class="gross" data-b="SEQUENZ">Startsequenz</button>
    <button data-b="GELB" id="k-gelb">Gelbphase</button>
    <button data-b="FRUEHSTART">Frühstart</button>
    <button data-b="TEST">Lampentest</button>
    <button data-b="LOS">Alles aus</button>
    <button class="stopp" data-b="ROT">Rot / Stopp</button>
  </div>
  <div class="karte">
    <div>Wartezeit vor Grün</div>
    <div class="regler"><input type="range" id="warte" min="0" max="10" step="1"><span class="wert" id="warte-wert"></span></div>
  </div>
  <div class="zeile fehler" id="fehler"></div>
</main><script>
const TEXTE = { gesperrt:'Gesperrt – Rot', vorstart:'Vorstart – Gelb', startsequenz:'Startsequenz läuft',
  rennen:'Rennen läuft', gelbphase:'Gelbphase', fruehstart:'Frühstart – Gelb blinkt' };
const reihe = (id, n, k) => { const el = document.getElementById(id);
  for (let i = 0; i < n; i++) { const d = document.createElement('div'); d.className = 'lampe ' + k; el.appendChild(d); } };
reihe('r-rot', 5, 'r'); reihe('r-gelb', 5, 'y'); reihe('r-gruen', 5, 'g');
let pin = ''; try { pin = localStorage.getItem('ampel-pin') || ''; } catch (e) {}
let stand = null, warteZiehen = false;
async function ruf(pfad, daten) {
  const r = await fetch(pfad, { method: daten ? 'POST' : 'GET', headers: { 'X-Pin': pin },
                                body: daten ? JSON.stringify(daten) : undefined, cache: 'no-store' });
  if (r.status === 401) { pin = prompt('PIN der Ampel') || ''; try { localStorage.setItem('ampel-pin', pin); } catch (e) {}
                          throw new Error('PIN nötig'); }
  if (!r.ok) throw new Error((await r.text()) || r.status);
  return r.json();
}
function zeigen(s) {
  stand = s;
  document.getElementById('zustand').textContent = (TEXTE[s.zustand] || s.zustand) + (s.omegasim ? ' · OmegaSim verbunden' : '');
  document.querySelectorAll('#r-rot .lampe').forEach(l => l.classList.toggle('an', s.rot));
  document.querySelectorAll('#r-gelb .lampe').forEach(l => l.classList.toggle('an', s.gelb));
  document.querySelectorAll('#r-gruen .lampe').forEach((l, i) => l.classList.toggle('an', i < s.gruen));
  document.getElementById('hinweis').hidden = !s.omegasim;
  document.querySelectorAll('button[data-b]').forEach(b => { b.disabled = s.omegasim && b.dataset.b !== 'ROT'; });
  const g = document.getElementById('k-gelb');
  g.dataset.b = s.zustand === 'gelbphase' ? 'GELB_AUS' : 'GELB';
  g.textContent = s.zustand === 'gelbphase' ? 'Gelbphase aufheben' : 'Gelbphase';
  if (s.omegasim) g.disabled = true;
  if (!warteZiehen) { document.getElementById('warte').value = s.warte; }
  document.getElementById('warte-wert').textContent = document.getElementById('warte').value + ' s';
  document.getElementById('fehler').textContent = '';
}
async function holen() { try { zeigen(await ruf('/status')); }
  catch (e) { document.getElementById('fehler').textContent = 'Keine Verbindung zur Ampel (' + e.message + ')'; } }
document.querySelectorAll('button[data-b]').forEach(b => b.addEventListener('click', async () => {
  try { zeigen(await ruf('/befehl', { befehl: b.dataset.b })); setTimeout(holen, 150); }
  catch (e) { document.getElementById('fehler').textContent = e.message; } }));
const w = document.getElementById('warte');
w.addEventListener('input', () => { warteZiehen = true; document.getElementById('warte-wert').textContent = w.value + ' s'; });
w.addEventListener('change', async () => { try { zeigen(await ruf('/einstellung', { warte: Number(w.value) })); }
  catch (e) { document.getElementById('fehler').textContent = e.message; } warteZiehen = false; });
holen(); setInterval(holen, 400);
</script></body></html>
"""


def einstellungen_laden():
    global SEQUENZ_WARTE_S
    try:
        import json
        pfad = os.path.join(os.path.dirname(os.path.abspath(__file__)), EINSTELLUNGEN_DATEI)
        with open(pfad, encoding="utf-8") as f:
            daten = json.load(f)
        if isinstance(daten.get("warte"), (int, float)):
            SEQUENZ_WARTE_S = max(0, min(10, daten["warte"]))
    except (OSError, ValueError):
        pass


def einstellungen_speichern():
    try:
        import json
        pfad = os.path.join(os.path.dirname(os.path.abspath(__file__)), EINSTELLUNGEN_DATEI)
        with open(pfad, "w", encoding="utf-8") as f:
            json.dump({"warte": SEQUENZ_WARTE_S}, f)
    except OSError as fehler:
        log(f"Einstellungen nicht gespeichert ({fehler}).")


def starte_web(ampel, schlange, port=None, adresse="0.0.0.0"):
    """Steuerseite im Hintergrund. Gibt den Server zurueck (fuer Tests)."""
    import json
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    port = WEB_PORT if port is None else port
    if port is None:
        return None

    class Seite(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _antwort(self, code, inhalt, art="application/json"):
            daten = inhalt.encode("utf-8") if isinstance(inhalt, str) else inhalt
            self.send_response(code)
            self.send_header("Content-Type", art + "; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(daten)))
            self.end_headers()
            self.wfile.write(daten)

        def _pin_ok(self):
            if WEB_PIN is None:
                return True
            if self.headers.get("X-Pin", "") == str(WEB_PIN):
                return True
            self._antwort(401, "PIN falsch", "text/plain")
            return False

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                return self._antwort(200, STEUERSEITE, "text/html")
            if self.path.startswith("/status"):
                if self._pin_ok():
                    self._antwort(200, json.dumps(ampel.zustand_json()))
                return
            self._antwort(404, "nicht gefunden", "text/plain")

        def do_POST(self):
            if not self._pin_ok():
                return
            try:
                laenge = int(self.headers.get("Content-Length", "0") or 0)
                daten = json.loads(self.rfile.read(min(laenge, 4096)) or b"{}")
            except ValueError:
                return self._antwort(400, "kein JSON", "text/plain")
            if self.path == "/befehl":
                befehl = str(daten.get("befehl", "")).upper()
                if befehl not in WEB_ERLAUBT:
                    return self._antwort(400, "unbekannter Befehl", "text/plain")
                extern_befehl(ampel, schlange, befehl, f"Steuerseite ({self.client_address[0]})")
                time.sleep(0.05)   # der Befehlsfaden ist schnell - so zeigt die Antwort schon den neuen Stand
                return self._antwort(200, json.dumps(ampel.zustand_json()))
            if self.path == "/einstellung":
                global SEQUENZ_WARTE_S
                w = daten.get("warte")
                if isinstance(w, (int, float)):
                    SEQUENZ_WARTE_S = max(0, min(10, w))
                    einstellungen_speichern()
                    log(f"Steuerseite: Wartezeit {SEQUENZ_WARTE_S} s")
                return self._antwort(200, json.dumps(ampel.zustand_json()))
            self._antwort(404, "nicht gefunden", "text/plain")

    try:
        server = ThreadingHTTPServer((adresse, port), Seite)
    except OSError as fehler:
        log(f"Steuerseite nicht moeglich ({fehler}).")
        return None
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    name = socket.gethostname()
    log(f"Steuerseite: http://{name}.local:{port}  (oder http://<IP-des-Pi>:{port})")
    return server


# ============================================================================
# ANSAGE
# ============================================================================


def ansage_abspielen():
    if not ANSAGE_AN:
        return
    ordner = os.path.dirname(os.path.abspath(__file__))
    datei = os.path.join(ordner, ANSAGE_DATEI) if ANSAGE_DATEI else None
    try:
        if datei and os.path.isfile(datei) and shutil.which("aplay"):
            subprocess.Popen(["aplay", "-q", datei])
        elif ANSAGE_TEXT and shutil.which("espeak-ng"):
            subprocess.Popen(["espeak-ng", "-v", "en", "-s", "140", ANSAGE_TEXT],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as fehler:
        log(f"Ansage nicht moeglich: {fehler}")


# ============================================================================
# BLUETOOTH LE UEBER BLUEZ / D-BUS
# ============================================================================


def nur_le_schalten():
    """Pi auf reines Bluetooth LE schalten (siehe NUR_LE). Braucht root und btmgmt (bluez)."""
    if not shutil.which("btmgmt"):
        log("btmgmt fehlt - klassisches Bluetooth bleibt an. Alternativ in "
            "/etc/bluetooth/main.conf: ControllerMode = le")
        return
    try:
        for schritt in (["power", "off"], ["bredr", "off"], ["le", "on"], ["power", "on"]):
            subprocess.run(["btmgmt", "-i", "hci0"] + schritt, capture_output=True, timeout=10)
        log("Bluetooth: nur LE (klassisches Bluetooth aus).")
    except (OSError, subprocess.SubprocessError) as fehler:
        log(f"Nur-LE nicht gesetzt: {fehler}")


def starte_ble(ampel, schlange):
    try:
        import dbus
        import dbus.mainloop.glib
        import dbus.service
        from gi.repository import GLib
    except ImportError:
        sys.exit("Fuer Bluetooth fehlen Pakete: sudo apt install python3-dbus python3-gi bluez")

    BLUEZ = "org.bluez"
    OM = "org.freedesktop.DBus.ObjectManager"
    PROPS = "org.freedesktop.DBus.Properties"
    GATT_MANAGER = "org.bluez.GattManager1"
    ADV_MANAGER = "org.bluez.LEAdvertisingManager1"
    GATT_SERVICE = "org.bluez.GattService1"
    GATT_CHRC = "org.bluez.GattCharacteristic1"
    LE_ADV = "org.bluez.LEAdvertisement1"
    BASIS = "/org/omegasim/ampel"

    class Anwendung(dbus.service.Object):
        def __init__(self, bus):
            self.path = BASIS
            self.dienste = []
            super().__init__(bus, self.path)

        @dbus.service.method(OM, out_signature="a{oa{sa{sv}}}")
        def GetManagedObjects(self):
            antwort = {}
            for d in self.dienste:
                antwort[d.get_path()] = d.props()
                for c in d.kanaele:
                    antwort[c.get_path()] = c.props()
            return antwort

    class Dienst(dbus.service.Object):
        def __init__(self, bus, uuid):
            self.path = BASIS + "/dienst0"
            self.uuid = uuid
            self.kanaele = []
            super().__init__(bus, self.path)

        def get_path(self):
            return dbus.ObjectPath(self.path)

        def props(self):
            return {GATT_SERVICE: {
                "UUID": self.uuid, "Primary": True,
                "Characteristics": dbus.Array([c.get_path() for c in self.kanaele], signature="o"),
            }}

        @dbus.service.method(PROPS, in_signature="s", out_signature="a{sv}")
        def GetAll(self, schnittstelle):
            return self.props()[GATT_SERVICE]

    class BefehlsKanal(dbus.service.Object):
        def __init__(self, bus, dienst, uuid):
            self.path = dienst.path + "/kanal0"
            self.dienst = dienst
            self.uuid = uuid
            super().__init__(bus, self.path)

        def get_path(self):
            return dbus.ObjectPath(self.path)

        def props(self):
            return {GATT_CHRC: {
                "Service": self.dienst.get_path(), "UUID": self.uuid,
                "Flags": dbus.Array(["write", "write-without-response"], signature="s"),
            }}

        @dbus.service.method(PROPS, in_signature="s", out_signature="a{sv}")
        def GetAll(self, schnittstelle):
            return self.props()[GATT_CHRC]

        @dbus.service.method(GATT_CHRC, in_signature="aya{sv}")
        def WriteValue(self, wert, optionen):
            # Ein BLE-Schreibvorgang ist ein ganzer Befehl - auch ohne Zeilenende.
            text = bytes(wert).decode("utf-8", errors="ignore")
            if not text.endswith(("\n", "\r", ";")):
                text += "\n"
            schlange.daten(text)

    class Werbung(dbus.service.Object):
        def __init__(self, bus):
            self.path = BASIS + "/werbung0"
            super().__init__(bus, self.path)

        def get_path(self):
            return dbus.ObjectPath(self.path)

        def props(self):
            return {LE_ADV: {
                "Type": "peripheral",
                "ServiceUUIDs": dbus.Array([AMPEL_SERVICE], signature="s"),
                "LocalName": dbus.String(BLE_NAME),
            }}

        @dbus.service.method(PROPS, in_signature="s", out_signature="a{sv}")
        def GetAll(self, schnittstelle):
            return self.props()[LE_ADV]

        @dbus.service.method(LE_ADV)
        def Release(self):
            log("Bluetooth-Werbung von BlueZ beendet.")

    class Kopplungsagent(dbus.service.Object):
        """Beantwortet Kopplungsanfragen ohne PIN ("Just Works"). Ohne Agent haengt eine
        Kopplung, die Android anstoesst, ins Leere, und BlueZ trennt die Verbindung."""
        AGENT = "org.bluez.Agent1"

        def __init__(self, bus):
            self.path = BASIS + "/agent"
            super().__init__(bus, self.path)

        @dbus.service.method(AGENT)
        def Release(self):
            pass

        @dbus.service.method(AGENT, in_signature="os")
        def AuthorizeService(self, geraet, uuid):
            log("Kopplung: Dienst freigegeben.")

        @dbus.service.method(AGENT, in_signature="o", out_signature="s")
        def RequestPinCode(self, geraet):
            return "0000"

        @dbus.service.method(AGENT, in_signature="o", out_signature="u")
        def RequestPasskey(self, geraet):
            return dbus.UInt32(0)

        @dbus.service.method(AGENT, in_signature="ouq")
        def DisplayPasskey(self, geraet, passkey, eingegeben):
            pass

        @dbus.service.method(AGENT, in_signature="os")
        def DisplayPinCode(self, geraet, pincode):
            pass

        @dbus.service.method(AGENT, in_signature="ou")
        def RequestConfirmation(self, geraet, passkey):
            log("Kopplung bestaetigt.")

        @dbus.service.method(AGENT, in_signature="o")
        def RequestAuthorization(self, geraet):
            log("Kopplung bestaetigt.")

        @dbus.service.method(AGENT)
        def Cancel(self):
            log("Kopplung vom Tablet abgebrochen.")

    if NUR_LE:
        nur_le_schalten()

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    adapter = None
    for pfad, schnitt in dbus.Interface(bus.get_object(BLUEZ, "/"), OM).GetManagedObjects().items():
        if GATT_MANAGER in schnitt and ADV_MANAGER in schnitt:
            adapter = pfad
            break
    if not adapter:
        sys.exit("Kein Bluetooth-LE-Adapter gefunden (laeuft bluetoothd?).")
    adapter_props = dbus.Interface(bus.get_object(BLUEZ, adapter), PROPS)
    adapter_props.Set("org.bluez.Adapter1", "Powered", dbus.Boolean(True))
    try:
        adapter_props.Set("org.bluez.Adapter1", "Pairable", dbus.Boolean(True))
    except dbus.DBusException as e:
        log(f"Pairable nicht gesetzt: {e}")

    agent = Kopplungsagent(bus)
    try:
        agenten = dbus.Interface(bus.get_object(BLUEZ, "/org/bluez"), "org.bluez.AgentManager1")
        agenten.RegisterAgent(agent.path, "NoInputNoOutput")
        agenten.RequestDefaultAgent(agent.path)
        log("Kopplungsagent aktiv (ohne PIN).")
    except dbus.DBusException as e:
        log(f"Kopplungsagent nicht angemeldet: {e}")

    app = Anwendung(bus)
    dienst = Dienst(bus, AMPEL_SERVICE)
    dienst.kanaele.append(BefehlsKanal(bus, dienst, AMPEL_BEFEHL))
    app.dienste.append(dienst)
    werbung = Werbung(bus)

    schleife = GLib.MainLoop()

    def fehler(was):
        def f(e):
            log(f"{was} fehlgeschlagen: {e}")
            schleife.quit()
        return f

    dbus.Interface(bus.get_object(BLUEZ, adapter), GATT_MANAGER).RegisterApplication(
        app.path, {}, reply_handler=lambda: log("GATT-Dienst angemeldet."),
        error_handler=fehler("GATT-Dienst anmelden"))
    dbus.Interface(bus.get_object(BLUEZ, adapter), ADV_MANAGER).RegisterAdvertisement(
        werbung.get_path(), {},
        reply_handler=lambda: log(f"Sichtbar als \"{BLE_NAME}\" - in OmegaSim verbinden."),
        error_handler=fehler("Werbung anmelden"))

    # Verbindungen beobachten: OmegaSim weg -> Rot (Sicherheit).
    def geraet_geaendert(schnittstelle, geaendert, _ungueltig, path=None):
        if schnittstelle != "org.bluez.Device1" or "Connected" not in geaendert:
            return
        if geaendert["Connected"]:
            log(f"Verbunden: {path}")
            ampel.omegasim_verbunden = True
            # Vertrauen, damit eine spaetere Verbindung ohne Rueckfrage geht.
            try:
                dbus.Interface(bus.get_object(BLUEZ, path), PROPS).Set(
                    "org.bluez.Device1", "Trusted", dbus.Boolean(True))
            except dbus.DBusException:
                pass
        else:
            log(f"Getrennt: {path}")
            ampel.omegasim_verbunden = False
            if BEI_VERBINDUNGSABBRUCH_ROT:
                schlange.zeile("ROT")

    bus.add_signal_receiver(geraet_geaendert, dbus_interface=PROPS,
                            signal_name="PropertiesChanged", path_keyword="path")
    schleife.run()


# ============================================================================
# TESTZUGAENGE: TCP / TASTATUR
# ============================================================================


def starte_tcp(schlange, port, adresse="0.0.0.0"):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((adresse, port))
    server.listen(4)
    log(f"Befehle per Netzwerk: {adresse}:{port}")
    while True:
        verbindung, von = server.accept()
        with verbindung:
            verbindung.settimeout(5)
            try:
                while True:
                    daten = verbindung.recv(1024)
                    if not daten:
                        break
                    schlange.daten(daten.decode("utf-8", errors="ignore"))
            except OSError:
                pass
        schlange.daten("\n")   # letzter Befehl auch ohne Zeilenende


def tcp_im_hintergrund(schlange):
    if TCP_PORT is None:
        return
    def lauf():
        try:
            starte_tcp(schlange, TCP_PORT, TCP_ADRESSE)
        except OSError as fehler:
            log(f"Netzwerk-Befehle nicht moeglich ({fehler}).")
    threading.Thread(target=lauf, daemon=True).start()


def befehl_senden(befehl):
    """--befehl: einen Befehl an das laufende Programm schicken (z. B. aus RaspController)."""
    if TCP_PORT is None:
        sys.exit("TCP_PORT ist aus - Befehle per Netzwerk abgeschaltet.")
    ziel = "127.0.0.1" if TCP_ADRESSE in ("0.0.0.0", "") else TCP_ADRESSE
    try:
        with socket.create_connection((ziel, TCP_PORT), timeout=3) as v:
            v.sendall((befehl.strip() + "\n").encode())
    except OSError as fehler:
        sys.exit(f"Ampel-Programm nicht erreichbar ({fehler}). Laeuft es?")
    print("gesendet:", befehl.strip())


def starte_tastatur(schlange, eingaenge=None):
    log("Befehle eingeben: ROT, START, GRUEN 2, LOS, FRUEHSTART, GELB, GELB_AUS, SEQUENZ, TEST; "
        "Eingang nachstellen: PIN 6 1. Strg+D beendet.")
    for zeile in sys.stdin:
        t = re.match(r"^\s*PIN\s+(\d+)\s+([01])\s*$", zeile, re.I)
        if t and eingaenge:
            eingaenge.signal(int(t.group(1)), t.group(2) == "1")
        else:
            schlange.daten(zeile)


# ============================================================================


def main():
    parser = argparse.ArgumentParser(description="Startampel fuer OmegaSim")
    parser.add_argument("--sim", action="store_true", help="ohne GPIO, Anzeige in der Konsole")
    gruppe = parser.add_mutually_exclusive_group()
    gruppe.add_argument("--stdin", action="store_true", help="Befehle ueber die Tastatur (statt Bluetooth)")
    gruppe.add_argument("--tcp", type=int, metavar="PORT", help="nur Befehle ueber TCP (statt Bluetooth)")
    gruppe.add_argument("--befehl", metavar="BEFEHL",
                        help="Befehl an das laufende Programm senden, z. B. --befehl SEQUENZ")
    parser.add_argument("--web", action="store_true", help="(Test) Steuerseite auch mit --stdin")
    parser.add_argument("--warte", type=float, metavar="S",
                        help="(Test) nach --stdin so lange weiterlaufen, z. B. fuer SEQUENZ")
    args = parser.parse_args()

    if args.befehl:
        return befehl_senden(args.befehl)

    einstellungen_laden()
    ampel = Ampel(simulation=args.sim)
    schlange = Befehlsschlange(ampel)
    eingaenge = Eingaenge(ampel, schlange, ampel.sim)
    if not args.stdin or args.web:
        starte_web(ampel, schlange)
    try:
        if args.stdin:
            starte_tastatur(schlange, eingaenge)
            schlange.daten("\n")
            schlange.q.join()
            if args.warte:
                time.sleep(args.warte)
        elif args.tcp:
            starte_tcp(schlange, args.tcp)
        else:
            tcp_im_hintergrund(schlange)
            starte_ble(ampel, schlange)
    except KeyboardInterrupt:
        pass
    finally:
        ampel.beenden()
        log("Beendet.")


if __name__ == "__main__":
    main()
