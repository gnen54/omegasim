# Startampel fuer OmegaSim - Raspberry Pi Pico W / Pico WH (MicroPython)
#
# Dieselbe Ampel wie tools/startampel/startampel.py (Raspberry Pi), nur auf dem Pico:
# gleicher Bluetooth-LE-Dienst, gleiche Befehle, gleiche Steuerseite. Die App merkt keinen
# Unterschied. Auf den Pico kopieren: diese Datei als main.py und steuerseite.html daneben;
# dann startet die Ampel bei jedem Einschalten.
#
# Aufbau der Ampel
#     Oben    : rote Reihe   (1 Kanal)
#     Mitte   : gelbe Reihe  (1 Kanal)
#     Unten   : gruene Reihe (5 Spalten, 5 Kanaele)
#
# Befehle (von OmegaSim per Bluetooth, von der Steuerseite, von den Eingaengen)
#     ROT          gesperrt, Rennende, Abbruch          -> Rot
#     START        Start in OmegaSim                    -> Gelb
#     GRUEN <n>    Ampelton (die App schickt 1 bis 5)   -> n gruene Spalten (+ Gelb)
#     LOS          Gruen / Start                        -> alles aus
#     FRUEHSTART   Fruehstart im Countdown              -> Gelb blinkt bis zum Neustart
#     GELB         Gelbe Flagge                         -> Gelb ...
#     GELB_AUS     ... bis zur Freigabe                 -> aus
#     SEQUENZ      eigene Startsequenz (ohne OmegaSim)  -> Gelb, Wartezeit, 1..5 Gruen, aus
#     TEST         Lampentest: 2 s alles an
#
# Betrieb ohne OmegaSim: vier Eingaenge ueber Optokoppler und eine Steuerseite im Browser
# (eigenes WLAN "Startampel" -> http://192.168.4.1). Ist OmegaSim verbunden, hat die App
# Vorrang: von aussen geht dann nur ROT.
#
# Die Ansage "Gentlemen, start your engines" spricht OmegaSim selbst - der Pico braucht
# keinen Ton.
#
# Onboard-LED: blinkt = wartet auf OmegaSim, an = OmegaSim verbunden.

import bluetooth
import json
import os
import select
import socket
import time
from machine import Pin, Timer
from micropython import const

try:
    import network
except ImportError:          # Pico ohne W: kein WLAN, alles andere geht
    network = None

# ============================================================================
# KONFIGURATION
# ============================================================================

# Ausgaenge (GPxx, nicht die Pin-Nummern am Rand). Jeder schaltet ueber einen Treiber
# (ULN2803 oder MOSFET) eine ganze Reihe bzw. Spalte - ein Pico-Pin liefert nur wenige mA.
PIN_ROT = 16
PIN_GELB = 17
PINS_GRUEN = (18, 19, 20, 21, 22)   # Spalte 1 .. 5, von links nach rechts

AKTIV_HIGH = True        # False, falls der Treiber bei LOW einschaltet
BLINK_TAKT_MS = 500      # Halbperiode beim Blinken (an/aus je 0,5 s)
GELB_WAEHREND_GRUEN = True

# Eigene Startsequenz (ohne OmegaSim): Gelb, Wartezeit, fuenf gruene Spalten im Takt, aus.
SEQUENZ_WARTE_S = 4      # aenderbar auf der Steuerseite, wird gespeichert
SEQUENZ_TAKT_MS = 1000

# Eingaenge ueber Optokoppler (PC817): (GPIO, Befehl, Art)
#   "puls"  = einmal beim Einschalten des Signals
#   "dauer" = solange das Signal anliegt; beim Abschalten der Gegenbefehl (GELB -> GELB_AUS)
# GP10..GP13 = Pins 14..17 am Rand, GND an Pin 13 oder 18.
EINGAENGE_AN = True
EINGAENGE = (
    (10, "SEQUENZ", "puls"),       # Start: eigene Startsequenz
    (11, "GELB", "dauer"),         # Gelbphase, solange das Signal anliegt
    (12, "ROT", "puls"),           # Rennende / Abbruch / Not-Aus
    (13, "FRUEHSTART", "puls"),    # Fruehstart
)
GEGENBEFEHL = {"GELB": "GELB_AUS"}
EINGANG_AKTIV_LOW = True   # Optokoppler zieht nach GND, interner Pull-up
ENTPRELL_MS = 50
OMEGASIM_VORRANG = True    # OmegaSim verbunden: von aussen nur ROT

# WLAN fuer die Steuerseite.
#   "eigenes" = der Pico macht ein eigenes WLAN auf (Handy damit verbinden, kein Router noetig)
#   "heim"    = der Pico meldet sich im Heim-WLAN an; klappt das nicht, macht er sein eigenes auf
#   None      = kein WLAN, keine Steuerseite
WLAN_MODUS = "eigenes"
EIGENES_WLAN_NAME = "Startampel"
EIGENES_WLAN_PASSWORT = "startampel"    # mindestens 8 Zeichen
HEIM_WLAN_NAME = ""
HEIM_WLAN_PASSWORT = ""
HOSTNAME = "startampel"                 # im Heim-WLAN ggf. http://startampel.local
WEB_PORT = 80
WEB_PIN = None                          # Zahl = Steuerseite fragt einmal danach

# Bluetooth LE - muss zu src/74-startampel.js passen.
BLE_NAME = "Ampel"
AMPEL_SERVICE = bluetooth.UUID("b5a30001-0e9a-4b7c-8d2f-a3f1c0de5a11")
AMPEL_BEFEHL = bluetooth.UUID("b5a30002-0e9a-4b7c-8d2f-a3f1c0de5a11")
BEI_VERBINDUNGSABBRUCH_ROT = True   # Sicherheit: App weg -> Rot

EINSTELLUNGEN_DATEI = "einstellungen.json"

# ============================================================================
# LEDs
# ============================================================================


class Ausgang:
    def __init__(self, nr):
        self.pin = Pin(nr, Pin.OUT)
        self.an = False
        self.aus()

    def ein(self):
        self.an = True
        self.pin.value(1 if AKTIV_HIGH else 0)

    def aus(self):
        self.an = False
        self.pin.value(0 if AKTIV_HIGH else 1)

    def setze(self, an):
        self.ein() if an else self.aus()


GESPERRT = "gesperrt"
VORSTART = "vorstart"
STARTSEQUENZ = "startsequenz"
RENNEN = "rennen"
GELBPHASE = "gelbphase"
FRUEHSTART = "fruehstart"

# Diese Befehle lassen eine laufende eigene Startsequenz weiterlaufen.
SEQUENZ_LAESST_LAUFEN = ("SEQUENZ", "STATUS", "TEST")


class Ampel:
    def __init__(self):
        self.rot = Ausgang(PIN_ROT)
        self.gelb = Ausgang(PIN_GELB)
        self.gruen = [Ausgang(n) for n in PINS_GRUEN]
        self.zustand = None
        self.gruen_anzahl = 0
        self.blinkt = False
        self._blink_an = False
        self._timer = Timer()
        self.seq_start = None        # ticks_ms beim Start der eigenen Sequenz, sonst None
        self.seq_schritt = 0
        self.test_bis = None         # Lampentest laeuft bis ...
        self.test_vorher = None
        self.omegasim_verbunden = False
        self.sperren()

    # ---------------------------------------------------------------- Helfer
    def _blink(self, _t):
        self._blink_an = not self._blink_an
        self.gelb.setze(self._blink_an)

    def _setze(self, rot=False, gelb=False, gruen=0, gelb_blinkt=False, aus_test=False):
        if not aus_test:
            self.test_bis = None
        self._timer.deinit()
        self.blinkt = False
        self.rot.setze(rot)
        self.gelb.setze(gelb)
        for i, led in enumerate(self.gruen):
            led.setze(i < gruen)
        self.gruen_anzahl = gruen
        if gelb_blinkt:
            self.blinkt = True
            self._blink_an = False
            self._timer.init(period=BLINK_TAKT_MS, mode=Timer.PERIODIC, callback=self._blink)
        self.anzeigen()

    def anzeigen(self):
        p = lambda an: "#" if an else "."
        gelb = "~" if self.blinkt else p(self.gelb.an)
        print("Rot", p(self.rot.an), "| Gelb", gelb, "| Gruen",
              "".join(p(l.an) for l in self.gruen), "  [" + str(self.zustand) + "]")

    def zustand_json(self):
        return {"zustand": self.zustand, "rot": self.rot.an, "gelb": self.gelb.an,
                "blinkt": self.blinkt, "gruen": self.gruen_anzahl,
                "omegasim": self.omegasim_verbunden, "sequenz": self.seq_start is not None,
                "warte": SEQUENZ_WARTE_S}

    # -------------------------------------------------------------- Aktionen
    def sperren(self, _n=None):
        self.zustand = GESPERRT
        self._setze(rot=True)

    def vorstart(self, _n=None):
        self.zustand = VORSTART
        self._setze(gelb=True)

    def gruen_weiter(self, n=None):
        if self.zustand not in (VORSTART, STARTSEQUENZ):
            print("GRUEN ignoriert (" + str(self.zustand) + ")")
            return
        neu = self.gruen_anzahl + 1 if n is None else n
        self.zustand = STARTSEQUENZ
        self._setze(gelb=GELB_WAEHREND_GRUEN, gruen=max(0, min(5, neu)))

    def los(self, _n=None):
        # Auch aus "gesperrt": freies Training startet ohne Countdown.
        if self.zustand not in (GESPERRT, VORSTART, STARTSEQUENZ):
            print("LOS ignoriert (" + str(self.zustand) + ")")
            return
        self.zustand = RENNEN
        self._setze()

    def fruehstart(self, _n=None):
        if self.zustand not in (VORSTART, STARTSEQUENZ):
            print("FRUEHSTART ignoriert (" + str(self.zustand) + ")")
            return
        self.zustand = FRUEHSTART
        self._setze(gelb_blinkt=True)

    def gelb_an(self, _n=None):
        if self.zustand not in (RENNEN, GELBPHASE):
            print("GELB ignoriert (" + str(self.zustand) + ")")
            return
        self.zustand = GELBPHASE
        self._setze(gelb=True)

    def gelb_aus(self, _n=None):
        if self.zustand != GELBPHASE:
            print("GELB_AUS ignoriert (" + str(self.zustand) + ")")
            return
        self.zustand = RENNEN
        self._setze()

    def sequenz(self, _n=None):
        if self.zustand not in (GESPERRT, FRUEHSTART, VORSTART) or self.seq_start is not None:
            print("SEQUENZ ignoriert (" + str(self.zustand) + ")")
            return
        print("Eigene Startsequenz.")
        self.vorstart()
        self.seq_start = time.ticks_ms()
        self.seq_schritt = 0

    def lampentest(self, _n=None):
        # Ohne Warten: die Hauptschleife stellt nach 2 s den vorherigen Stand wieder her.
        # Kommt vorher ein anderer Befehl, gilt der.
        if self.test_bis is None:
            self.test_vorher = (self.rot.an, self.gelb.an, self.gruen_anzahl, self.blinkt)
        self._setze(rot=True, gelb=True, gruen=5, aus_test=True)
        self.test_bis = time.ticks_add(time.ticks_ms(), 2000)

    def status(self, _n=None):
        self.anzeigen()

    def tick(self):
        """Aus der Hauptschleife: Lampentest beenden, eigene Sequenz weiterschalten."""
        jetzt = time.ticks_ms()
        if self.test_bis is not None and time.ticks_diff(jetzt, self.test_bis) >= 0:
            r, g, n, b = self.test_vorher
            self.test_bis = None
            self._setze(rot=r, gelb=g, gruen=n, gelb_blinkt=b)
        if self.seq_start is None:
            return
        if self.zustand not in (VORSTART, STARTSEQUENZ):
            self.seq_start = None          # abgebrochen (ROT, FRUEHSTART, ...)
            print("Startsequenz abgebrochen.")
            return
        t = time.ticks_diff(jetzt, self.seq_start) - SEQUENZ_WARTE_S * 1000
        soll = 0 if t < 0 else t // SEQUENZ_TAKT_MS + 1     # 1..5 Gruen, 6 = LOS
        while self.seq_schritt < min(soll, 6):
            self.seq_schritt += 1
            if self.seq_schritt <= 5:
                self.gruen_weiter(self.seq_schritt)
            else:
                self.seq_start = None
                self.los()

    # ------------------------------------------------------------- Befehle
    def befehl(self, zeile):
        zeile = zeile.strip().upper()
        if not zeile:
            return
        teile = zeile.split()
        name = teile[0]
        zahl = None
        if len(teile) > 1 and teile[1].isdigit():
            zahl = int(teile[1])
        elif name.startswith("GRUEN") and name[5:].isdigit():   # "GRUEN3"
            zahl = int(name[5:])
            name = "GRUEN"
        aktion = BEFEHLE.get(name)
        if aktion is None:
            print("Unbekannter Befehl:", zeile)
            return
        print("Befehl:", zeile)
        if name not in SEQUENZ_LAESST_LAUFEN and self.seq_start is not None:
            self.seq_start = None
            print("Startsequenz abgebrochen.")
        aktion(self, zahl)


BEFEHLE = {
    "ROT": Ampel.sperren,
    "START": Ampel.vorstart,
    "GRUEN": Ampel.gruen_weiter,
    "LOS": Ampel.los,
    "FRUEHSTART": Ampel.fruehstart,
    "GELB": Ampel.gelb_an,
    "GELB_AUS": Ampel.gelb_aus,
    "SEQUENZ": Ampel.sequenz,
    "TEST": Ampel.lampentest,
    "STATUS": Ampel.status,
}


def extern_befehl(ampel, befehl, quelle):
    """Befehl von aussen (Eingang, Steuerseite). Ist OmegaSim verbunden, gilt nur ROT."""
    if OMEGASIM_VORRANG and ampel.omegasim_verbunden and befehl != "ROT":
        print(quelle + ": " + befehl + " ignoriert - OmegaSim ist verbunden.")
        return False
    print(quelle + ": " + befehl)
    ampel.befehl(befehl)
    return True


# ============================================================================
# EINGAENGE (Optokoppler)
# ============================================================================


class Eingaenge:
    """Fragt die Eingaenge in der Hauptschleife ab und entprellt sie (Wert muss ENTPRELL_MS
    stabil sein, bevor er zaehlt)."""

    def __init__(self, ampel):
        self.ampel = ampel
        self.liste = []
        if not EINGAENGE_AN:
            return
        zug = Pin.PULL_UP if EINGANG_AKTIV_LOW else Pin.PULL_DOWN
        for gpio, befehl, art in EINGAENGE:
            pin = Pin(gpio, Pin.IN, zug)
            aktiv = self._aktiv(pin)
            # [gpio, befehl, art, pin, gueltiger Stand, Rohstand, Rohstand seit]
            self.liste.append([gpio, befehl, art, pin, aktiv, aktiv, time.ticks_ms()])
        print("Eingaenge: " + ", ".join("GP%d=%s" % (e[0], e[1]) for e in self.liste))

    @staticmethod
    def _aktiv(pin):
        v = pin.value()
        return (v == 0) if EINGANG_AKTIV_LOW else (v == 1)

    def tick(self):
        jetzt = time.ticks_ms()
        for e in self.liste:
            roh = self._aktiv(e[3])
            if roh != e[5]:
                e[5] = roh
                e[6] = jetzt
            elif roh != e[4] and time.ticks_diff(jetzt, e[6]) >= ENTPRELL_MS:
                e[4] = roh
                self.signal(e, roh)

    def signal(self, e, aktiv):
        gpio, befehl, art = e[0], e[1], e[2]
        if not aktiv:
            if art != "dauer" or befehl not in GEGENBEFEHL:
                return
            befehl = GEGENBEFEHL[befehl]
        extern_befehl(self.ampel, befehl, "Eingang GP%d" % gpio)


# ============================================================================
# WLAN UND STEUERSEITE
# ============================================================================

# Die Seite liegt als eigene Datei neben main.py auf dem Pico und wird beim Abruf
# haeppchenweise vom Flash gesendet - als Text im Programm kostete sie dauerhaft Arbeitsspeicher,
# und der ist mit Bluetooth und WLAN knapp.
STEUERSEITE_DATEI = "steuerseite.html"

WEB_ERLAUBT = ("SEQUENZ", "ROT", "GELB", "GELB_AUS", "FRUEHSTART", "TEST", "LOS")


def einstellungen_laden():
    global SEQUENZ_WARTE_S
    try:
        with open(EINSTELLUNGEN_DATEI) as f:
            w = json.load(f).get("warte")
        if isinstance(w, (int, float)):
            SEQUENZ_WARTE_S = max(0, min(10, w))
    except (OSError, ValueError):
        pass


def einstellungen_speichern():
    try:
        with open(EINSTELLUNGEN_DATEI, "w") as f:
            json.dump({"warte": SEQUENZ_WARTE_S}, f)
    except OSError as fehler:
        print("Einstellungen nicht gespeichert:", fehler)


def wlan_starten():
    """WLAN nach WLAN_MODUS. Gibt die IP zurueck oder None."""
    if network is None or WLAN_MODUS is None:
        return None
    try:
        if hasattr(network, "hostname"):
            network.hostname(HOSTNAME)
    except Exception:
        pass
    if WLAN_MODUS == "heim" and HEIM_WLAN_NAME:
        sta = network.WLAN(network.STA_IF)
        sta.active(True)
        sta.connect(HEIM_WLAN_NAME, HEIM_WLAN_PASSWORT)
        bis = time.ticks_add(time.ticks_ms(), 15000)
        while not sta.isconnected() and time.ticks_diff(bis, time.ticks_ms()) > 0:
            time.sleep_ms(200)
        if sta.isconnected():
            ip = sta.ifconfig()[0]
            print("Heim-WLAN verbunden. Steuerseite: http://" + ip
                  + (":" + str(WEB_PORT) if WEB_PORT != 80 else "")
                  + "  (oder http://" + HOSTNAME + ".local)")
            return ip
        print("Heim-WLAN nicht erreichbar - mache eigenes WLAN auf.")
        sta.active(False)
    ap = network.WLAN(network.AP_IF)
    ap.config(essid=EIGENES_WLAN_NAME, password=EIGENES_WLAN_PASSWORT)
    ap.active(True)
    ip = ap.ifconfig()[0]
    print("Eigenes WLAN \"" + EIGENES_WLAN_NAME + "\" (Passwort: " + EIGENES_WLAN_PASSWORT
          + "). Steuerseite: http://" + ip + (":" + str(WEB_PORT) if WEB_PORT != 80 else ""))
    return ip


class Steuerseite:
    """Kleiner Webserver ohne Faeden: die Hauptschleife fragt per poll(0), ob jemand anklopft,
    und beantwortet eine Anfrage am Stueck (Zeitlimit 1 s)."""

    def __init__(self, ampel, port=WEB_PORT, adresse="0.0.0.0"):
        self.ampel = ampel
        self.server = socket.socket()
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(socket.getaddrinfo(adresse, port)[0][-1])
        self.server.listen(2)
        self.server.setblocking(False)
        self.poll = select.poll()
        self.poll.register(self.server, select.POLLIN)

    def schritt(self):
        for _ in self.poll.poll(0):
            try:
                kunde, adresse = self.server.accept()
            except OSError:
                return
            try:
                kunde.settimeout(1.0)
                self._anfrage(kunde, adresse)
            except Exception as fehler:
                print("Steuerseite:", fehler)
            finally:
                kunde.close()

    def _lesen(self, kunde):
        daten = b""
        while b"\r\n\r\n" not in daten and len(daten) < 4096:
            stueck = kunde.recv(512)
            if not stueck:
                break
            daten += stueck
        kopf, _, rumpf = daten.partition(b"\r\n\r\n")
        zeilen = kopf.decode().split("\r\n")
        teile = zeilen[0].split(" ")
        methode = teile[0] if teile else ""
        pfad = teile[1] if len(teile) > 1 else "/"
        felder = {}
        for z in zeilen[1:]:
            k, _, v = z.partition(":")
            felder[k.strip().lower()] = v.strip()
        laenge = min(int(felder.get("content-length", "0") or 0), 2048)
        while len(rumpf) < laenge:
            stueck = kunde.recv(512)
            if not stueck:
                break
            rumpf += stueck
        return methode, pfad, felder, rumpf

    def _senden(self, kunde, code, inhalt, art="application/json"):
        if isinstance(inhalt, str):
            inhalt = inhalt.encode()
        text = {200: "OK", 400: "Bad Request", 401: "Unauthorized", 404: "Not Found"}.get(code, "OK")
        kopf = ("HTTP/1.0 %d %s\r\nContent-Type: %s; charset=utf-8\r\nCache-Control: no-store\r\n"
                "Content-Length: %d\r\nConnection: close\r\n\r\n") % (code, text, art, len(inhalt))
        senden = kunde.sendall if hasattr(kunde, "sendall") else kunde.write
        senden(kopf.encode())
        senden(inhalt)

    def _datei(self, kunde, name, art):
        try:
            groesse = os.stat(name)[6]
        except OSError:
            return self._senden(kunde, 404, name + " fehlt auf dem Pico - bitte mitkopieren.", "text/plain")
        senden = kunde.sendall if hasattr(kunde, "sendall") else kunde.write
        senden((("HTTP/1.0 200 OK\r\nContent-Type: %s; charset=utf-8\r\nCache-Control: no-store\r\n"
                 "Content-Length: %d\r\nConnection: close\r\n\r\n") % (art, groesse)).encode())
        puffer = bytearray(512)
        with open(name, "rb") as f:
            while True:
                n = f.readinto(puffer)
                if not n:
                    break
                senden(puffer[:n])

    def _anfrage(self, kunde, adresse):
        global SEQUENZ_WARTE_S
        methode, pfad, felder, rumpf = self._lesen(kunde)
        if methode == "GET" and pfad in ("/", "/index.html"):
            return self._datei(kunde, STEUERSEITE_DATEI, "text/html")
        if WEB_PIN is not None and felder.get("x-pin", "") != str(WEB_PIN):
            return self._senden(kunde, 401, "PIN falsch", "text/plain")
        if methode == "GET" and pfad.startswith("/status"):
            return self._senden(kunde, 200, json.dumps(self.ampel.zustand_json()))
        if methode == "POST":
            try:
                daten = json.loads(rumpf or b"{}")
            except ValueError:
                return self._senden(kunde, 400, "kein JSON", "text/plain")
            if pfad == "/befehl":
                befehl = str(daten.get("befehl", "")).upper()
                if befehl not in WEB_ERLAUBT:
                    return self._senden(kunde, 400, "unbekannter Befehl", "text/plain")
                extern_befehl(self.ampel, befehl, "Steuerseite")
                return self._senden(kunde, 200, json.dumps(self.ampel.zustand_json()))
            if pfad == "/einstellung":
                w = daten.get("warte")
                if isinstance(w, (int, float)):
                    SEQUENZ_WARTE_S = max(0, min(10, w))
                    einstellungen_speichern()
                    print("Steuerseite: Wartezeit", SEQUENZ_WARTE_S, "s")
                return self._senden(kunde, 200, json.dumps(self.ampel.zustand_json()))
        self._senden(kunde, 404, "nicht gefunden", "text/plain")


# ============================================================================
# BLUETOOTH LE
# ============================================================================

_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE = const(3)
_FLAG_WRITE = const(0x0008)
_FLAG_WRITE_NO_RESPONSE = const(0x0004)


def werbung(name, dienst):
    """Werbedaten: Flags, 128-Bit-Dienst-UUID, Name - 3 + 18 + 2+len(name) Byte, also bis
    zu 10 Zeichen Name in den 31 Byte."""
    daten = bytearray(b"\x02\x01\x06")
    u = bytes(dienst)
    daten += bytes((len(u) + 1, 0x07)) + u
    n = name.encode()
    daten += bytes((len(n) + 1, 0x09)) + n
    return bytes(daten)


class Funk:
    def __init__(self, ampel):
        self.ampel = ampel
        self.eingang = []          # Befehlszeilen aus dem IRQ, abgearbeitet in der Hauptschleife
        self.rest = ""
        self.verbunden = set()
        self.led = Pin("LED", Pin.OUT)
        self.ble = bluetooth.BLE()
        self.ble.active(True)
        self.ble.config(gap_name=BLE_NAME)
        self.ble.irq(self._irq)
        ((self.befehl_handle,),) = self.ble.gatts_register_services((
            (AMPEL_SERVICE, ((AMPEL_BEFEHL, _FLAG_WRITE | _FLAG_WRITE_NO_RESPONSE),)),
        ))
        # Platz fuer laengere Schreibvorgaenge (Standard waeren 20 Byte).
        self.ble.gatts_set_buffer(self.befehl_handle, 64, True)
        self._adv = werbung(BLE_NAME, AMPEL_SERVICE)
        self.werben()

    def werben(self):
        self.ble.gap_advertise(200000, adv_data=self._adv)   # alle 200 ms
        print("Sichtbar als \"" + BLE_NAME + "\" - in OmegaSim verbinden.")

    # Der IRQ macht so wenig wie moeglich: Zeilen merken, Rest in der Hauptschleife.
    def _irq(self, ereignis, daten):
        if ereignis == _IRQ_CENTRAL_CONNECT:
            self.verbunden.add(daten[0])
            self.eingang.append(("+", None))
        elif ereignis == _IRQ_CENTRAL_DISCONNECT:
            self.verbunden.discard(daten[0])
            self.eingang.append(("-", None))
        elif ereignis == _IRQ_GATTS_WRITE:
            if daten[1] == self.befehl_handle:
                text = bytes(self.ble.gatts_read(self.befehl_handle)).decode()
                # Ein Schreibvorgang ist ein ganzer Befehl - auch ohne Zeilenende.
                if text[-1:] not in ("\n", "\r", ";"):
                    text += "\n"
                self.eingang.append(("t", text))

    def schritt(self):
        """Aus der Hauptschleife: alles abarbeiten, was der IRQ gesammelt hat."""
        while self.eingang:
            art, text = self.eingang.pop(0)
            if art == "+":
                print("Verbunden.")
                self.ampel.omegasim_verbunden = True
                self.led.on()
            elif art == "-":
                print("Getrennt.")
                self.ampel.omegasim_verbunden = bool(self.verbunden)
                if BEI_VERBINDUNGSABBRUCH_ROT:
                    self.ampel.befehl("ROT")
                if not self.verbunden:
                    self.werben()
            else:
                self.rest += text
                for z in "\r;":
                    self.rest = self.rest.replace(z, "\n")
                zeilen = self.rest.split("\n")
                self.rest = zeilen.pop()          # unvollstaendiger Rest
                for zeile in zeilen:
                    self.ampel.befehl(zeile)
        # Onboard-LED: blinken, solange niemand verbunden ist.
        if not self.verbunden:
            self.led.value((time.ticks_ms() // 500) % 2)


def main():
    einstellungen_laden()
    ampel = Ampel()
    funk = Funk(ampel)
    eingaenge = Eingaenge(ampel)
    seite = None
    try:
        if wlan_starten() is not None:
            seite = Steuerseite(ampel)
    except Exception as fehler:
        print("Steuerseite nicht moeglich:", fehler)
    while True:
        funk.schritt()
        eingaenge.tick()
        ampel.tick()
        if seite:
            seite.schritt()
        time.sleep_ms(10)


if __name__ == "__main__":
    main()
