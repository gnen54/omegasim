  // ============================== STARTAMPEL (Raspberry Pi, Bluetooth LE) ==============================
  //
  // BESTELLT: eine echte Startampel am Tisch, angesteuert von OmegaSim per Bluetooth. Drei
  // LED-Reihen: oben Rot, in der Mitte Gelb, unten Gruen mit fuenf Spalten.
  //
  //   gesperrt (kein Training/Rennen freigegeben)   Rot
  //   Start im Fenster "Autos in Position"          Rot aus, Gelb an; OmegaSim sagt
  //                                                 "Gentlemen, start your engines"
  //   Starttoene des Countdowns                     Gruen, Spalte fuer Spalte dazu
  //   Gruen / Los                                   alles aus
  //   Fruehstart im Countdown                       Gruen aus, Gelb blinkt bis zum Neustart
  //   Gelbe Flagge im Rennen                        Gelb, bis sie aufgehoben ist
  //   Rennende oder Abbruch                         wieder Rot
  //
  // PROTOKOLL: Textzeilen mit "\n" auf eine schreibbare Characteristic eines EIGENEN Dienstes.
  // Nicht der Nordic-UART-Dienst der Autos: garageConnect() filtert auch nach diesem, und die
  // Ampel stuende dann im Auto-Verbinden-Dialog. Der Gegenpart ist das Ampel-Programm
  // auf Raspberry Pi bzw. Pico (separat, nicht Teil dieses Repositorys).
  //
  //   ROT | START | GRUEN <1-5> | LOS | FRUEHSTART | GELB | GELB_AUS
  //
  // FUENF TOENE, FUENF SPALTEN: der Countdown hat fuenf Toene im Sekundentakt (ampelZeitplan()
  // in 70-race.js), je Ton leuchtet eine gruene Spalte mehr - wie die Bruecke im Cockpit.
  const AMPEL_SERVICE = 'b5a30001-0e9a-4b7c-8d2f-a3f1c0de5a11';
  const AMPEL_BEFEHL = 'b5a30002-0e9a-4b7c-8d2f-a3f1c0de5a11';
  let ampelGeraet = null, ampelKanal = null;
  let ampelSchlange = Promise.resolve();
  // Ob die Ampel gerade im Vorstart steht (Gelb). START kommt beim Oeffnen des Startfensters;
  // startRaceCountdown() schickt es nur nach, wenn es dort nicht kam (Challenge, Mehrspieler).
  let ampelVorstart = false;
  // Countdown mit fester Gruenzeit (WLAN-Mehrspieler, Challenge-Fenster): dort laeuft die Ampel
  // auf allen Geraeten gleichzeitig, ein Abbruch hier wuerde nur dieses Geraet anhalten.
  let ampelZeitgesteuert = false;

  function ampelVerbunden() {
    return !!(ampelKanal && ampelGeraet && ampelGeraet.gatt && ampelGeraet.gatt.connected);
  }
  function ampelNeustartAn() { const el = $('race-ampel-neustart'); return el ? !!el.checked : true; }

  // Befehle laufen nacheinander: Bluetooth vertraegt keinen zweiten Schreibvorgang, solange der
  // erste noch offen ist, und die Reihenfolge (START vor GRUEN) muss am Pi ankommen, wie sie
  // hier gemeint war.
  //
  // GEMELDET: "START kommt am Pi an, GRUEN 1..5 und ROT nicht." Die Schlange hing: ein
  // Schreiben MIT Antwort, dessen Bestaetigung nie kommt (Android-Bluetooth), haelt jeden
  // weiteren Befehl fuer immer auf. Deshalb jetzt:
  //  - OHNE Antwort schreiben, wenn die Ampel das anbietet (Pi und Pico tun es) - da gibt es
  //    nichts, worauf man warten koennte;
  //  - sonst mit Antwort, aber hoechstens AMPEL_SCHREIB_MS lang warten;
  //  - ein fehlgeschlagener Befehl wird einmal wiederholt (z. B. "GATT operation already in
  //    progress", solange der haengende noch offen ist);
  //  - jeder Befehl steht im Protokoll, damit man am Tablet sieht, was hinausging.
  const AMPEL_SCHREIB_MS = 1500;
  function ampelSchreiben(kanal, daten) {
    const p = kanal.properties || {};
    // In der Android-App (05-app-bruecke.js) am schnellen Autoweg vorbei, der nur den jeweils
    // neuesten Befehl schreibt.
    if (p.writeWithoutResponse && typeof kanal._befehlSchreiben === 'function') return kanal._befehlSchreiben(daten);
    if (p.writeWithoutResponse && typeof kanal.writeValueWithoutResponse === 'function') {
      return kanal.writeValueWithoutResponse(daten);
    }
    const schreiben = typeof kanal.writeValueWithResponse === 'function'
      ? kanal.writeValueWithResponse(daten) : kanal.writeValue(daten);
    return Promise.race([schreiben, new Promise((_, nein) =>
      setTimeout(() => nein(new Error('keine Antwort in ' + AMPEL_SCHREIB_MS + ' ms')), AMPEL_SCHREIB_MS))]);
  }
  function ampelSenden(befehl) {
    if (befehl === 'ROT' || befehl === 'LOS' || befehl === 'FRUEHSTART') ampelVorstart = false;
    else if (befehl === 'START') ampelVorstart = true;
    if (!ampelVerbunden()) {
      if (ampelGeraet) log('Startampel: ' + befehl + ' nicht gesendet (nicht verbunden)', 'err');
      return;
    }
    const kanal = ampelKanal;
    const daten = new TextEncoder().encode(befehl + '\n');
    ampelSchlange = ampelSchlange
      .then(() => ampelSchreiben(kanal, daten))
      .catch(() => new Promise((r) => setTimeout(r, 150)).then(() => ampelSchreiben(kanal, daten)))
      .then(() => { log('Startampel: ' + befehl, 'info'); ampelLetzter = befehl; ampelFehler = ''; ampelStatusZeigen(); })
      .catch((e) => {
        ampelFehler = befehl + ': ' + ((e && e.message) || e);
        log('Startampel: ' + befehl + ' nicht gesendet (' + ((e && e.message) || e) + ')', 'err');
        ampelStatusZeigen();
      });
  }

  // Nach dem Verbinden den Stand der App nachziehen - die Ampel weiss sonst nicht, ob gerade
  // ein Rennen laeuft.
  function ampelStandSenden() {
    const live = raceState === 'racing' || raceState === 'finishing';
    if (live) {
      ampelSenden('LOS');
      if (typeof flagState !== 'undefined' && flagState !== 'green') ampelSenden('GELB');
    } else if (raceState === 'countdown' || (typeof raceGridOffen === 'function' && raceGridOffen())) {
      ampelSenden('START');
    } else {
      ampelSenden('ROT');
    }
  }

  // Zur Fehlersuche am Tisch: der zuletzt gesendete Befehl und der letzte Fehler stehen direkt
  // unter "Startampel verbinden" (Optionen -> AddOn).
  let ampelLetzter = '', ampelFehler = '';
  // Erkennungszeichen der Fassung: so sieht man am Tablet sofort, ob die neue Version geladen ist
  // (die Programmversion 1.0.36 aendert sich bei Testfassungen nicht).
  const AMPEL_STAND = '18.10.-e';
  function ampelStatusZeigen(text) {
    const s = $('ampel-status');
    let zeile = text || (ampelVerbunden()
      ? t('Verbunden: {n}').replace('{n}', (ampelGeraet && ampelGeraet.name) || 'Startampel')
      : t('Nicht verbunden.'));
    if (!text && ampelLetzter) zeile += ' · ' + t('zuletzt') + ': ' + ampelLetzter;
    if (!text && ampelFehler) zeile += ' · ⚠ ' + ampelFehler;
    if (!text) zeile += ' · (' + AMPEL_STAND + ')';
    if (s) s.textContent = zeile;
    const b = $('ampel-verbinden');
    if (b) b.textContent = ampelVerbunden() ? t('Trennen') : t('Verbinden');
  }

  // Bricht die Verbindung ab (Funkloch, Pi kurz weg), verbindet OmegaSim von selbst neu - ohne
  // Auswahlfenster, dasselbe Geraet - und schickt den aktuellen Stand. Fuenf Versuche.
  let ampelVonHandGetrennt = false;
  async function ampelWiederVerbinden(dev, versuch) {
    if (ampelGeraet !== dev || ampelVonHandGetrennt || ampelVerbunden() || versuch > 5) return;
    ampelStatusZeigen(t('Verbinde neu …'));
    try {
      const srv = await dev.gatt.connect();
      const dienst = await srv.getPrimaryService(AMPEL_SERVICE);
      ampelKanal = await dienst.getCharacteristic(AMPEL_BEFEHL);
      log('Startampel wieder verbunden.', 'info');
      ampelStatusZeigen();
      ampelStandSenden();
    } catch (e) {
      ampelStatusZeigen();
      setTimeout(() => ampelWiederVerbinden(dev, versuch + 1), 2000);
    }
  }

  async function ampelVerbinden() {
    if (ampelVerbunden()) {
      ampelVonHandGetrennt = true;
      try { ampelGeraet.gatt.disconnect(); } catch (e) { /* schon weg */ }
      return;
    }
    ampelVonHandGetrennt = false;
    if (!navigator.bluetooth) { alert(t('Dieser Browser kann kein Bluetooth.')); return; }
    try {
      ampelStatusZeigen(t('Suche …'));
      const dev = await navigator.bluetooth.requestDevice({
        filters: [{ services: [AMPEL_SERVICE] }],
        optionalServices: [AMPEL_SERVICE],
      });
      const srv = await dev.gatt.connect();
      const dienst = await srv.getPrimaryService(AMPEL_SERVICE);
      ampelKanal = await dienst.getCharacteristic(AMPEL_BEFEHL);
      ampelGeraet = dev;
      dev.addEventListener('gattserverdisconnected', () => {
        if (ampelGeraet !== dev) return;
        ampelKanal = null;
        ampelSchlange = Promise.resolve();
        log('Startampel getrennt.', 'err');
        ampelStatusZeigen();
        if (!ampelVonHandGetrennt) ampelWiederVerbinden(dev, 1);
      });
      log('Startampel verbunden.', 'info');
      ampelStatusZeigen();
      ampelStandSenden();
    } catch (err) {
      ampelKanal = null;
      ampelStatusZeigen();
      if (err && err.name === 'NotFoundError') log('Keine Startampel gewaehlt.', 'info');
      else log('Startampel: Verbinden fehlgeschlagen: ' + (err && err.message), 'err');
    }
  }
  if ($('ampel-verbinden')) $('ampel-verbinden').addEventListener('click', ampelVerbinden);

  // ---- Die Aufrufe aus dem Rennablauf (70-race.js, 90-ghosts.js) ----
  // Startfenster abgebrochen: Rot (bleibt Rot, falls schon Rot).
  function ampelStartAbgebrochen() { ampelSenden('ROT'); }
  // Der Countdown beginnt. Kam der Start nicht ueber den Knopf im Startfenster (Mehrspieler-
  // Countdown), fehlt START noch - dann Gelb ohne Ansage.
  function ampelCountdown(zeitgesteuert) {
    ampelZeitgesteuert = !!zeitgesteuert;
    if (!ampelVorstart) ampelSenden('START');
  }
  // DER EIGENTLICHE START: der Start-Knopf im Fenster "Bringe die Autos in Position"
  // (raceGridStart() in 70-race.js - Tippen und Controller-Taste X laufen beide dort durch).
  //
  // BESTELLT: "Nur im Menue 'Bringe die Autos in Position' dieser Start-Button soll den
  // eigentlichen Start ausloesen." Erst hier geht die Ampel auf Gelb, und erst hier sagt
  // OmegaSim "Gentlemen, start your engines" (80-sound.js) - nicht schon beim Oeffnen des
  // Fensters ("Rennen starten", Cockpit-Knopf, Challenge nach Stillstand), nicht beim
  // Mehrspieler-Countdown. Und nur, wenn nichts laeuft. Auch ohne verbundene Ampel.
  function ampelStartKnopf(beginn) {
    if (raceState !== 'idle' && raceState !== 'finished') return false;
    ampelSenden('START');
    return typeof startAnsageSprechen === 'function' && startAnsageSprechen(beginn);
  }
  // ---- WARTEZEIT zwischen Start und erstem gruenen Licht ----
  //
  // BESTELLT: "Wir brauchen ein Delay (3-5 Sekunden) nach Betaetigen des Start-Buttons bis
  // zum Beginn der Sequenz der gruenen LEDs." Nach dem Start im Fenster steht die Ampel auf
  // Gelb, die Ansage laeuft, und erst nach dieser Zeit beginnt der Countdown (der erste Ton =
  // die ersten gruenen Spalten). Einstellbar unter Optionen -> AddOn, ab Werk 4 s, 0 = aus.
  //
  // Waehrend des Wartens laeuft noch nichts (raceState bleibt idle): ein zweites Startfenster
  // wird nicht geoeffnet, und der Start-Knopf im Cockpit bricht das Warten ab (Ampel Rot).
  const START_WARTE_STORE = 'omegasim-start-warte-s', START_WARTE_VORGABE = 4;
  let startWarteTimer = null;
  function startWarteMs() {
    const el = $('race-start-warte');
    const v = el ? parseFloat(el.value) : START_WARTE_VORGABE;
    return (Number.isFinite(v) ? Math.max(0, Math.min(10, v)) : START_WARTE_VORGABE) * 1000;
  }
  function ampelStartWartet() { return !!startWarteTimer; }
  // Aus raceGridStart() (70-race.js): Gelb und Ansage sofort, der Countdown (weiter) danach.
  //
  // DIE WARTEZEIT BEGINNT MIT DER ANSAGE, nicht mit dem Knopf: beim ersten Start braucht die
  // Sprachausgabe auf Android Sekunden, bis sie spricht, und die Ampel war dann schon durch.
  // Jetzt laeuft die Uhr erst ab dem ersten gesprochenen Wort (oder sofort, wenn es keine
  // Ansage gibt) - spaetestens aber nach ANSAGE_MAX_MS, damit eine haengende Stimme den
  // Start nicht blockiert. 4 s statt vorher 10 s: am Tisch wirkten 10 s wie "Gruen kommt nicht".
  const ANSAGE_MAX_MS = 4000;
  let startWarteNr = 0;
  function ampelStartVerzoegert(weiter) {
    if (startWarteTimer) return;
    const nr = ++startWarteNr;
    const ms = startWarteMs();
    let laeuft = false;
    const uhrStarten = () => {
      if (laeuft || nr !== startWarteNr || !startWarteTimer) return;   // schon gestartet/abgebrochen
      laeuft = true;
      clearTimeout(startWarteTimer);
      startWarteTimer = setTimeout(() => {
        startWarteTimer = null;
        weiter();
        // Lief der Start nicht an (z. B. Time Attack ohne eingescannte Strecke, Knockout ohne
        // NPC - dort erscheint ein Hinweis), darf die Ampel nicht ewig auf Gelb stehen.
        if (raceState === 'idle' || raceState === 'finished') {
          ampelSenden('ROT');
          if ($('race-status').textContent.indexOf('…') >= 0) $('race-status').textContent = t('Start abgebrochen');
          if ($('race-stop-btn')) $('race-stop-btn').disabled = true;
          if ($('race-start-btn')) $('race-start-btn').disabled = false;
        }
        updateRaceActButtons();
      }, ms);
    };
    // Platzhalter, damit das Warten ab jetzt zaehlt (kein zweites Fenster, Abbrechen geht).
    startWarteTimer = setTimeout(uhrStarten, ANSAGE_MAX_MS);
    $('race-status').textContent = t('Start in {n} s …').replace('{n}', String(Math.round(ms / 1000)));
    // Schon im Warten abbrechbar (GEMELDET: "Rennabbruch per OmegaSim funktioniert nicht" -
    // der Knopf war bis zum Countdown gesperrt). requestRaceStop() bricht dann das Warten ab.
    if ($('race-stop-btn')) $('race-stop-btn').disabled = false;
    updateRaceActButtons();
    if (!ampelStartKnopf(uhrStarten)) uhrStarten();
  }
  function ampelStartWarteAbbrechen() {
    if (!startWarteTimer) return;
    clearTimeout(startWarteTimer);
    startWarteTimer = null;
    startWarteNr++;
    ampelSenden('ROT');
    if ($('race-stop-btn')) $('race-stop-btn').disabled = true;
    if ($('race-start-btn')) $('race-start-btn').disabled = false;
    $('race-status').textContent = t('Start abgebrochen');
    showHudToast(t('Start abgebrochen'));
    updateRaceActButtons();
  }
  if ($('race-start-warte')) {
    const el = $('race-start-warte');
    const zeigen = () => { if ($('race-start-warte-val')) $('race-start-warte-val').textContent = Math.round(startWarteMs() / 1000) + ' s'; };
    try { const w = localStorage.getItem(START_WARTE_STORE); if (w !== null && w !== '') el.value = w; } catch (e) { /* privat */ }
    el.addEventListener('input', () => {
      zeigen();
      try { localStorage.setItem(START_WARTE_STORE, el.value); } catch (e) { /* privat */ }
    });
    zeigen();
  }

  // Ein Ampelton: licht = Zahl der leuchtenden Spalten, 1..5 (70-race.js).
  function ampelTon(licht) {
    ampelSenden('GRUEN ' + Math.max(1, Math.min(5, licht)));
  }
  function ampelLos() { ampelSenden('LOS'); }
  function ampelRennende() { ampelSenden('ROT'); }
  function ampelGelb(an) { ampelSenden(an ? 'GELB' : 'GELB_AUS'); }

  // FRUEHSTART. Ohne Startampel bleibt alles, wie es war: die Ampel laeuft weiter, Strafe nach
  // den Renneinstellungen. MIT Startampel und eingeschaltetem Schalter wird der Start
  // abgebrochen - Gelb blinkt am Tisch, und "Rennen starten" beginnt die Abfolge neu.
  // Nicht im Mehrspieler und nicht in einer Challenge: dort haengt Gruen an einer Zeit, die
  // andere Geraete oder die Challenge vorgeben.
  // Rueckgabe true: der Start ist abgebrochen.
  function ampelFruehstart() {
    if (!ampelVerbunden() || !ampelNeustartAn() || ampelZeitgesteuert) return false;
    if (typeof challengeLaeuft === 'function' && challengeLaeuft()) return false;
    if (raceState !== 'countdown') return false;
    ampelSenden('FRUEHSTART');
    if (raceCountdownTimer) { clearTimeout(raceCountdownTimer); raceCountdownTimer = null; }
    ampelPlan = null; ampelSchritt = null;
    setRaceLights(0);
    fruehstartReset();
    raceState = 'idle';
    $('race-start-btn').disabled = false;
    $('race-stop-btn').disabled = true;
    $('race-status').textContent = t('Frühstart – bitte neu starten');
    showHudToast(t('Frühstart – Start abgebrochen'));
    log('Fruehstart: Start abgebrochen, die Startampel blinkt gelb. Rennen neu starten.', 'err');
    updateRaceActButtons();
    return true;
  }

  ampelStatusZeigen();
