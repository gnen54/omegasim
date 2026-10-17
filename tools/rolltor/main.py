# Rolltor-Steuerung - Raspberry Pi Pico W / Pico WH (MicroPython)
#
# Zwei Modell-Rolltore mit je einem Schrittmotor 28BYJ-48 (5 V) an einem ULN2803.
#   - Kalibrieren im Tippbetrieb (Halten = fahren, Loslassen = stehen)
#   - Endlagen "Zu" und "Auf" speichern, danach fahren die Tore genau dorthin
#   - Bedienung im Browser: http://rolltor.local (Heim-WLAN)
#   - Siri: Kurzbefehle rufen Adressen wie http://rolltor.local/tor/1/auf auf
#
# Auf den Pico kopieren: diese Datei als main.py und seite.html daneben.
#
# Position ohne Endschalter: der Pico zaehlt die Schritte und speichert die Position nach
# jeder Fahrt. Faellt der Strom MITTEN in einer Fahrt aus, weiss er beim Neustart nicht,
# wo das Tor steht - dann sperrt er Auf/Zu, bis man die Position im Kalibriermodus
# bestaetigt hat ("Tor steht jetzt auf Zu").
#
# Im Stillstand sind die Spulen stromlos: das Getriebe des 28BYJ-48 haelt selbst, und so
# wird nichts warm.

import json
import os
import select
import socket
import time
from machine import Pin, Timer

try:
    import network
except ImportError:          # Pico ohne W: keine Bedienung moeglich
    network = None

# ============================================================================
# KONFIGURATION
# ============================================================================

# Je Tor die vier GPIOs zum ULN2803 (Eingaenge 1-4 bzw. 5-8). Reihenfolge = Motoradern
# blau, rosa, gelb, orange (rot ist +5 V). "umkehren" dreht die Laufrichtung, falls das Tor
# beim Druck auf "Auf" nach unten faehrt - das geht auch auf der Seite.
TORE = (
    {"name": "Tor 1", "pins": (2, 3, 4, 5), "umkehren": False},
    {"name": "Tor 2", "pins": (6, 7, 8, 9), "umkehren": False},
)

# Geschwindigkeit. Der Schritt-Timer laeuft mit TAKT_HZ; ein Halbschritt dauert so viele
# Takte. 4096 Halbschritte = eine Umdrehung der Abtriebswelle.
#   2 Takte bei 1000 Hz = 2 ms je Halbschritt = ca. 7 U/min (sicher, kraeftig)
#   1 Takt               = 1 ms                 = ca. 14 U/min (Grenze, kann Schritte verlieren)
TAKT_HZ = 1000
TAKTE_FAHRT = 2          # Betrieb (Auf/Zu)
TAKTE_TIPPEN = 3         # Tippbetrieb, etwas langsamer zum genauen Einstellen
TAKTE_ANLAUF = 4         # die ersten Schritte jeder Fahrt langsamer (Anlauf)
ANLAUF_SCHRITTE = 16
FEINSCHRITT = 32         # Knoepfe "+/- fein" im Kalibriermodus
TIPP_TOTMANN_MS = 700    # Tippen stoppt, wenn so lange kein "weiter" kommt (WLAN weg o. ae.)

# WLAN. Fuer Siri muss der Pico im Heim-WLAN sein (iPhone im selben WLAN).
HEIM_WLAN_NAME = ""
HEIM_WLAN_PASSWORT = ""
HOSTNAME = "rolltor"                 # -> http://rolltor.local
# Ist das Heim-WLAN nicht erreichbar, macht der Pico ein eigenes auf (Bedienung im Browser
# geht dann trotzdem, Siri nicht): Handy mit "Rolltore" verbinden, http://192.168.4.1
EIGENES_WLAN_NAME = "Rolltore"
EIGENES_WLAN_PASSWORT = "rolltore"   # mindestens 8 Zeichen
WEB_PORT = 80
WEB_PIN = None                       # Zahl = Seite und Siri-Adressen brauchen die PIN

DATEI = "tore.json"
SEITE_DATEI = "seite.html"

# ============================================================================
# SCHRITTMOTOR
# ============================================================================

# Halbschritt-Folge fuer 28BYJ-48 (unipolar, 4 Spulen).
HALBSCHRITT = ((1, 0, 0, 0), (1, 1, 0, 0), (0, 1, 0, 0), (0, 1, 1, 0),
               (0, 0, 1, 0), (0, 0, 1, 1), (0, 0, 0, 1), (1, 0, 0, 1))


class Tor:
    """Ein Tor. pos zaehlt Halbschritte; +1 = Richtung "Auf" (nach dem Umkehren-Schalter)."""

    def __init__(self, nr, cfg):
        self.nr = nr
        self.name = cfg["name"]
        self.pins = [Pin(p, Pin.OUT, value=0) for p in cfg["pins"]]
        self.umkehren = cfg.get("umkehren", False)
        self.pos = 0
        self.zu = None
        self.auf = None
        self.unsicher = False          # Strom fiel mitten in einer Fahrt aus
        self.ziel = None               # Fahrt auf eine Position
        self.tipp = 0                  # Tippbetrieb: -1 / 0 / +1
        self.tipp_bis = 0
        self.takt = 0
        self.seit_start = 0
        self.faehrt = False
        self.ereignis = None           # "start" / "stopp" -> Hauptschleife speichert

    # ------------------------------------------------------------- Zustand
    def kalibriert(self):
        return self.zu is not None and self.auf is not None and self.zu != self.auf

    def prozent(self):
        if not self.kalibriert():
            return None
        p = (self.pos - self.zu) * 100 // (self.auf - self.zu)
        return max(0, min(100, p))

    def status(self):
        ziel, tipp = self.ziel, self.tipp      # einmal lesen - der Timer aendert sie nebenher
        richtung = 0
        if self.faehrt:
            richtung = tipp or (1 if ziel is not None and ziel > self.pos else -1)
        if self.faehrt and tipp:
            text = "Tippbetrieb"
        elif self.unsicher:
            text = "Position unsicher"
        elif not self.kalibriert():
            text = "fährt" if self.faehrt else "nicht kalibriert"
        elif self.faehrt:
            text = "fährt auf" if ziel == self.auf else "fährt zu" if ziel == self.zu else "fährt"
        elif self.pos == self.auf:
            text = "offen"
        elif self.pos == self.zu:
            text = "geschlossen"
        else:
            text = "halb offen"
        return {"nr": self.nr, "name": self.name, "pos": self.pos, "zu": self.zu, "auf": self.auf,
                "kalibriert": self.kalibriert(), "unsicher": self.unsicher, "faehrt": self.faehrt,
                "richtung": richtung, "prozent": self.prozent(), "umkehren": self.umkehren,
                "text": text}

    # ------------------------------------------------------------- Befehle
    def fahre(self, wohin):
        """'auf' / 'zu' / 'umschalten'. Gibt (ok, Text fuer Siri) zurueck."""
        if self.unsicher:
            return False, self.name + ": Position unsicher - bitte im Kalibriermodus bestätigen."
        if not self.kalibriert():
            return False, self.name + " ist noch nicht kalibriert."
        if wohin == "umschalten":
            mitte = (self.zu + self.auf) / 2
            naeher_auf = abs(self.pos - self.auf) < abs(self.pos - self.zu)
            if self.faehrt and self.ziel is not None:
                wohin = "zu" if self.ziel == self.auf else "auf"
            else:
                wohin = "zu" if naeher_auf or self.pos == mitte else "auf"
        ziel = self.auf if wohin == "auf" else self.zu
        self.tipp = 0
        if self.pos == ziel and not self.faehrt:
            return True, self.name + " ist schon " + ("offen." if wohin == "auf" else "geschlossen.")
        self.ziel = ziel
        return True, self.name + (" fährt auf." if wohin == "auf" else " fährt zu.")

    def stopp(self):
        self.ziel = None
        self.tipp = 0
        return True, self.name + " gestoppt."

    def tippen(self, richtung):
        """Tippbetrieb (Kalibrieren): faehrt, solange alle paar 100 ms 'weiter' kommt."""
        self.ziel = None
        self.tipp = max(-1, min(1, int(richtung)))
        self.tipp_bis = time.ticks_add(time.ticks_ms(), TIPP_TOTMANN_MS)

    def feinschritt(self, n):
        self.tipp = 0
        self.ziel = self.pos + int(n)

    def kalibrieren(self, was):
        if self.faehrt:
            return False, "Erst anhalten."
        if was == "zu_speichern":
            self.zu = self.pos
        elif was == "auf_speichern":
            self.auf = self.pos
        elif was == "hier_zu":            # nach Stromausfall: Tor steht auf "Zu"
            if self.zu is None:
                return False, "Zu ist noch nicht gespeichert."
            self.pos = self.zu
        elif was == "hier_auf":
            if self.auf is None:
                return False, "Auf ist noch nicht gespeichert."
            self.pos = self.auf
        elif was == "umkehren":
            # Andere Drehrichtung: die gespeicherten Endlagen passen nicht mehr.
            self.umkehren = not self.umkehren
            self.zu = self.auf = None
        elif was == "vergessen":
            self.zu = self.auf = None
        else:
            return False, "unbekannt"
        if was in ("zu_speichern", "auf_speichern", "hier_zu", "hier_auf"):
            self.unsicher = False
        self.ereignis = "stopp"            # speichern
        return True, "ok"

    # ------------------------------------------------- im Takt (Timer-Callback)
    def _richtung(self):
        if self.tipp:
            if time.ticks_diff(time.ticks_ms(), self.tipp_bis) > 0:
                self.tipp = 0               # Totmann: nichts mehr gehoert
                return 0
            return self.tipp
        if self.ziel is None:
            return 0
        if self.ziel == self.pos:
            self.ziel = None
            return 0
        return 1 if self.ziel > self.pos else -1

    def _spulen(self, werte):
        for pin, w in zip(self.pins, werte):
            pin.value(w)

    def takt_schritt(self):
        r = self._richtung()
        if r == 0:
            if self.faehrt:
                self.faehrt = False
                self._spulen((0, 0, 0, 0))    # stromlos - das Getriebe haelt
                self.ereignis = "stopp"
            return
        if not self.faehrt:
            self.faehrt = True
            self.takt = 0
            self.seit_start = 0
            self.ereignis = "start"
            self._spulen(HALBSCHRITT[self._phase(self.pos)])   # Spulen auf die aktuelle Lage
        self.takt += 1
        noetig = TAKTE_ANLAUF if self.seit_start < ANLAUF_SCHRITTE else (
            TAKTE_TIPPEN if self.tipp else TAKTE_FAHRT)
        if self.takt < noetig:
            return
        self.takt = 0
        self.seit_start += 1
        self.pos += r
        self._spulen(HALBSCHRITT[self._phase(self.pos)])

    def _phase(self, pos):
        return (-pos if self.umkehren else pos) % 8

    # ------------------------------------------------------------- Speichern
    def daten(self):
        return {"pos": self.pos, "zu": self.zu, "auf": self.auf, "umkehren": self.umkehren,
                "faehrt": self.faehrt}

    def laden(self, d):
        self.pos = int(d.get("pos", 0))
        self.zu = d.get("zu")
        self.auf = d.get("auf")
        self.umkehren = bool(d.get("umkehren", self.umkehren))
        self.unsicher = bool(d.get("faehrt", False))


def speichern(tore):
    """Erst in eine Hilfsdatei, dann umbenennen - so bleibt bei Stromausfall waehrend des
    Schreibens die alte Datei heil."""
    try:
        with open(DATEI + ".neu", "w") as f:
            json.dump({"tore": [t.daten() for t in tore]}, f)
        try:
            os.remove(DATEI)
        except OSError:
            pass
        os.rename(DATEI + ".neu", DATEI)
    except OSError as fehler:
        print("Speichern fehlgeschlagen:", fehler)


def laden(tore):
    for name in (DATEI, DATEI + ".neu"):
        try:
            with open(name) as f:
                liste = json.load(f).get("tore", [])
            for t, d in zip(tore, liste):
                t.laden(d)
            for t in tore:
                if t.unsicher:
                    print(t.name + ": Strom fiel waehrend einer Fahrt aus - Position unsicher.")
            return
        except (OSError, ValueError):
            continue
    print("Noch keine gespeicherten Positionen - bitte kalibrieren.")


# ============================================================================
# WLAN UND WEBSEITE (inkl. Siri-Adressen)
# ============================================================================


def wlan_starten():
    """Heim-WLAN, sonst eigenes. Gibt (ip, modus) zurueck."""
    if network is None:
        return None, None
    try:
        if hasattr(network, "hostname"):
            network.hostname(HOSTNAME)
    except Exception:
        pass
    if HEIM_WLAN_NAME:
        sta = network.WLAN(network.STA_IF)
        sta.active(True)
        sta.connect(HEIM_WLAN_NAME, HEIM_WLAN_PASSWORT)
        bis = time.ticks_add(time.ticks_ms(), 20000)
        while not sta.isconnected() and time.ticks_diff(bis, time.ticks_ms()) > 0:
            time.sleep_ms(200)
        if sta.isconnected():
            ip = sta.ifconfig()[0]
            print("Heim-WLAN verbunden: http://" + HOSTNAME + ".local  oder  http://" + ip)
            return ip, "heim"
        print("Heim-WLAN nicht erreichbar - mache eigenes WLAN auf.")
        sta.active(False)
    ap = network.WLAN(network.AP_IF)
    ap.config(essid=EIGENES_WLAN_NAME, password=EIGENES_WLAN_PASSWORT)
    ap.active(True)
    ip = ap.ifconfig()[0]
    print("Eigenes WLAN \"" + EIGENES_WLAN_NAME + "\" (Passwort: " + EIGENES_WLAN_PASSWORT
          + "): http://" + ip)
    return ip, "eigenes"


def abfrage_werte(pfad):
    """'/tor/1/auf?pin=12' -> ('/tor/1/auf', {'pin': '12'})"""
    pfad, _, rest = pfad.partition("?")
    werte = {}
    for teil in rest.split("&"):
        k, _, v = teil.partition("=")
        if k:
            werte[k] = v
    return pfad, werte


class Webseite:
    """Kleiner Webserver ohne Faeden: die Hauptschleife fragt per poll(0), ob jemand anklopft,
    und beantwortet eine Anfrage am Stueck (Zeitlimit 1 s)."""

    def __init__(self, tore, modus, port=WEB_PORT, adresse="0.0.0.0"):
        self.tore = tore
        self.modus = modus
        self.server = socket.socket()
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(socket.getaddrinfo(adresse, port)[0][-1])
        self.server.listen(3)
        self.server.setblocking(False)
        self.poll = select.poll()
        self.poll.register(self.server, select.POLLIN)

    def schritt(self):
        for _ in self.poll.poll(0):
            try:
                kunde, _adr = self.server.accept()
            except OSError:
                return
            try:
                kunde.settimeout(1.0)
                self._anfrage(kunde)
            except Exception as fehler:
                print("Webseite:", fehler)
            finally:
                kunde.close()

    # ------------------------------------------------------------- HTTP
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
        text = {200: "OK", 400: "Bad Request", 401: "Unauthorized", 404: "Not Found",
                409: "Conflict"}.get(code, "OK")
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

    def _status(self):
        return json.dumps({"tore": [t.status() for t in self.tore], "wlan": self.modus,
                           "host": HOSTNAME})

    def _tore(self, wer):
        if wer == "alle":
            return list(self.tore)
        try:
            n = int(wer)
        except (TypeError, ValueError):
            return []
        return [t for t in self.tore if t.nr == n]

    # ------------------------------------------------------------- Routen
    def _anfrage(self, kunde):
        methode, voll, felder, rumpf = self._lesen(kunde)
        pfad, werte = abfrage_werte(voll)
        if methode == "GET" and pfad in ("/", "/index.html"):
            return self._datei(kunde, SEITE_DATEI, "text/html")
        if WEB_PIN is not None and felder.get("x-pin", werte.get("pin", "")) != str(WEB_PIN):
            return self._senden(kunde, 401, "PIN falsch", "text/plain")

        # Siri / Kurzbefehle: GET /tor/<1|2|alle>/<auf|zu|stopp|umschalten> -> Text zum Vorlesen
        if methode == "GET" and pfad.startswith("/tor/"):
            teile = pfad.strip("/").split("/")
            if len(teile) != 3 or teile[2] not in ("auf", "zu", "stopp", "umschalten"):
                return self._senden(kunde, 404, "Unbekannt. Beispiel: /tor/1/auf", "text/plain")
            tore = self._tore(teile[1])
            if not tore:
                return self._senden(kunde, 404, "Kein Tor " + teile[1] + ".", "text/plain")
            antworten = []
            for t in tore:
                ok, text = t.stopp() if teile[2] == "stopp" else t.fahre(teile[2])
                antworten.append(text)
            print("Siri/Adresse:", pfad)
            return self._senden(kunde, 200, " ".join(antworten), "text/plain")

        if methode == "GET" and pfad == "/status":
            return self._senden(kunde, 200, self._status())

        if methode == "POST":
            try:
                d = json.loads(rumpf or b"{}")
            except ValueError:
                return self._senden(kunde, 400, "kein JSON", "text/plain")
            tore = self._tore(str(d.get("tor", "")))
            if not tore:
                return self._senden(kunde, 400, "welches Tor?", "text/plain")
            if pfad == "/befehl":
                aktion = d.get("aktion")
                for t in tore:
                    if aktion == "stopp":
                        t.stopp()
                    elif aktion in ("auf", "zu", "umschalten"):
                        ok, text = t.fahre(aktion)
                        if not ok:
                            return self._senden(kunde, 409, text, "text/plain")
                    else:
                        return self._senden(kunde, 400, "unbekannte Aktion", "text/plain")
                return self._senden(kunde, 200, self._status())
            if pfad == "/tippen":
                for t in tore:
                    t.tippen(d.get("r", 0))
                return self._senden(kunde, 200, self._status())
            if pfad == "/fein":
                for t in tore:
                    t.feinschritt(FEINSCHRITT if int(d.get("r", 1)) > 0 else -FEINSCHRITT)
                return self._senden(kunde, 200, self._status())
            if pfad == "/kalibrieren":
                for t in tore:
                    ok, text = t.kalibrieren(d.get("was"))
                    if not ok:
                        return self._senden(kunde, 409, text, "text/plain")
                return self._senden(kunde, 200, self._status())
        self._senden(kunde, 404, "nicht gefunden", "text/plain")


# ============================================================================
# HAUPTSCHLEIFE
# ============================================================================


def main():
    tore = [Tor(i + 1, cfg) for i, cfg in enumerate(TORE)]
    laden(tore)
    for t in tore:
        print(t.name + ":", t.status()["text"], "- Position", t.pos)

    # Schritt-Timer: alle 1/TAKT_HZ s ein Takt fuer jedes Tor.
    def takt(_t):
        for t in tore:
            t.takt_schritt()
    timer = Timer()
    timer.init(freq=TAKT_HZ, mode=Timer.PERIODIC, callback=takt)

    led = Pin("LED", Pin.OUT)
    ip, modus = wlan_starten()
    seite = None
    if ip:
        try:
            seite = Webseite(tore, modus)
        except Exception as fehler:
            print("Webseite nicht moeglich:", fehler)

    while True:
        if seite:
            seite.schritt()
        for t in tore:
            e = t.ereignis
            if e:
                t.ereignis = None
                speichern(tore)          # bei "start" mit faehrt=True: Absicherung Stromausfall
                if e == "stopp":
                    print(t.name + ":", t.status()["text"], "- Position", t.pos)
        # Onboard-LED: an = Heim-WLAN, blinkt = eigenes WLAN, aus = kein WLAN
        if modus == "heim":
            led.on()
        elif modus == "eigenes":
            led.value((time.ticks_ms() // 500) % 2)
        time.sleep_ms(5)


if __name__ == "__main__":
    main()
