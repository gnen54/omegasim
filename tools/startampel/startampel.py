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
    sudo python3 startampel.py            # Bluetooth LE, echte LEDs
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
}

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
            # Vertrauen, damit eine spaetere Verbindung ohne Rueckfrage geht.
            try:
                dbus.Interface(bus.get_object(BLUEZ, path), PROPS).Set(
                    "org.bluez.Device1", "Trusted", dbus.Boolean(True))
            except dbus.DBusException:
                pass
        else:
            log(f"Getrennt: {path}")
            if BEI_VERBINDUNGSABBRUCH_ROT:
                schlange.zeile("ROT")

    bus.add_signal_receiver(geraet_geaendert, dbus_interface=PROPS,
                            signal_name="PropertiesChanged", path_keyword="path")
    schleife.run()


# ============================================================================
# TESTZUGAENGE: TCP / TASTATUR
# ============================================================================


def starte_tcp(schlange, port):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", port))
    server.listen(1)
    log(f"Warte auf TCP-Verbindung (Port {port}) ...")
    while True:
        verbindung, adresse = server.accept()
        log(f"Verbunden: {adresse[0]}")
        with verbindung:
            while True:
                daten = verbindung.recv(1024)
                if not daten:
                    break
                schlange.daten(daten.decode("utf-8", errors="ignore"))
        log(f"Getrennt: {adresse[0]}")


def starte_tastatur(schlange):
    log("Befehle eingeben: ROT, START, GRUEN 2, LOS, FRUEHSTART, GELB, GELB_AUS, TEST. Strg+D beendet.")
    for zeile in sys.stdin:
        schlange.daten(zeile)


# ============================================================================


def main():
    parser = argparse.ArgumentParser(description="Startampel fuer OmegaSim")
    parser.add_argument("--sim", action="store_true", help="ohne GPIO, Anzeige in der Konsole")
    gruppe = parser.add_mutually_exclusive_group()
    gruppe.add_argument("--stdin", action="store_true", help="Befehle ueber die Tastatur")
    gruppe.add_argument("--tcp", type=int, metavar="PORT", help="Befehle ueber TCP (Test)")
    args = parser.parse_args()

    ampel = Ampel(simulation=args.sim)
    schlange = Befehlsschlange(ampel)
    try:
        if args.stdin:
            starte_tastatur(schlange)
            schlange.daten("\n")
            schlange.q.join()
        elif args.tcp:
            starte_tcp(schlange, args.tcp)
        else:
            starte_ble(ampel, schlange)
    except KeyboardInterrupt:
        pass
    finally:
        ampel.beenden()
        log("Beendet.")


if __name__ == "__main__":
    main()
