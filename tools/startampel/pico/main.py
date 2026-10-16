# Startampel fuer OmegaSim - Raspberry Pi Pico W / Pico WH (MicroPython)
#
# Dieselbe Ampel wie tools/startampel/startampel.py (Raspberry Pi), nur auf dem Pico:
# gleicher Bluetooth-LE-Dienst, gleiche Befehle, gleiche UUIDs. Die App merkt keinen
# Unterschied. Als main.py auf den Pico kopieren, dann startet sie bei jedem Einschalten.
#
# Aufbau der Ampel
#     Oben    : rote Reihe   (1 Kanal)
#     Mitte   : gelbe Reihe  (1 Kanal)
#     Unten   : gruene Reihe (5 Spalten, 5 Kanaele)
#
# Befehle von OmegaSim (Text, ein Befehl je Schreibvorgang)
#     ROT          gesperrt, Rennende, Abbruch          -> Rot
#     START        "Rennen starten"                     -> Gelb
#     GRUEN <n>    Ampelton (die App schickt 2, 3, 5)   -> n gruene Spalten (+ Gelb)
#     LOS          Gruen / Start                        -> alles aus
#     FRUEHSTART   Fruehstart im Countdown              -> Gelb blinkt bis START
#     GELB         Gelbe Flagge                         -> Gelb ...
#     GELB_AUS     ... bis zur Freigabe                 -> aus
#     TEST         Lampentest: 2 s alles an
#
# Unterschied zum Raspberry Pi: der Pico hat keinen Ton, also keine Ansage
# "Gentlemen, start your engines" (siehe README, Abschnitt Pico).
#
# Die Onboard-LED zeigt den Bluetooth-Zustand: blinkt = wartet auf OmegaSim, an = verbunden.

import bluetooth
import time
from machine import Pin, Timer
from micropython import const

# ============================================================================
# KONFIGURATION
# ============================================================================

# GPIO-Nummern (GPxx, nicht die Pin-Nummern am Rand). Jeder Ausgang schaltet ueber einen
# Treiber (ULN2803 oder MOSFET) eine ganze Reihe bzw. Spalte - die 3,3-V-Pins des Pico
# liefern nur wenige mA.
PIN_ROT = 16
PIN_GELB = 17
PINS_GRUEN = (18, 19, 20, 21, 22)   # Spalte 1 .. 5, von links nach rechts

AKTIV_HIGH = True        # False, falls der Treiber bei LOW einschaltet
BLINK_TAKT_MS = 500      # Halbperiode beim Blinken (an/aus je 0,5 s)
GELB_WAEHREND_GRUEN = True

# Bluetooth LE - muss zu src/74-startampel.js passen.
BLE_NAME = "Ampel"
AMPEL_SERVICE = bluetooth.UUID("b5a30001-0e9a-4b7c-8d2f-a3f1c0de5a11")
AMPEL_BEFEHL = bluetooth.UUID("b5a30002-0e9a-4b7c-8d2f-a3f1c0de5a11")
BEI_VERBINDUNGSABBRUCH_ROT = True   # Sicherheit: App weg -> Rot

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
        self.sperren()

    # ---------------------------------------------------------------- Helfer
    def _blink(self, _t):
        self._blink_an = not self._blink_an
        self.gelb.setze(self._blink_an)

    def _setze(self, rot=False, gelb=False, gruen=0, gelb_blinkt=False):
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

    def lampentest(self, _n=None):
        vorher = (self.rot.an, self.gelb.an, self.gruen_anzahl, self.blinkt)
        self._setze(rot=True, gelb=True, gruen=5)
        time.sleep_ms(2000)
        self._setze(rot=vorher[0], gelb=vorher[1], gruen=vorher[2], gelb_blinkt=vorher[3])

    def status(self, _n=None):
        self.anzeigen()

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
        aktion(self, zahl)


BEFEHLE = {
    "ROT": Ampel.sperren,
    "START": Ampel.vorstart,
    "GRUEN": Ampel.gruen_weiter,
    "LOS": Ampel.los,
    "FRUEHSTART": Ampel.fruehstart,
    "GELB": Ampel.gelb_an,
    "GELB_AUS": Ampel.gelb_aus,
    "TEST": Ampel.lampentest,
    "STATUS": Ampel.status,
}

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
                self.led.on()
            elif art == "-":
                print("Getrennt.")
                if BEI_VERBINDUNGSABBRUCH_ROT:
                    self.ampel.sperren()
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
    ampel = Ampel()
    funk = Funk(ampel)
    while True:
        funk.schritt()
        time.sleep_ms(20)


if __name__ == "__main__":
    main()
