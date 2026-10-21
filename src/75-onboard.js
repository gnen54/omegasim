  // ============================== ONBOARD-KAMERA (FPV im Auto) ==============================
  //
  // BESTELLT: "kostenguenstig mit einem Carrera Hybrid Fahrzeug Streckenvideos erstellen,
  // Ausgabe moeglichst auf einem Bildschirm" - und als schoenste Fassung: "das Bild in
  // OmegaSim". Im Auto sitzt eine analoge FPV-Mikrokamera (5,8 GHz, Kamera + Sender in
  // einem, 3-5 g, eigener 1S-Akku), am Tablet/PC ein USB-Empfaenger (UVC). Der meldet sich
  // wie eine WEBCAM - also braucht es hier nichts als getUserMedia, keine eigene Hardware-
  // Schnittstelle wie bei der Startampel.
  //
  //   Optionen -> AddOn -> Onboard-Kamera     Einschalten, Kamera waehlen, Bild drehen
  //   Cockpit, Schirm "Onboard"               Livebild mit Runde, Zeit, km/h
  //   Aufnahme (Knopf oder Waehltaste X)      Video MIT Anzeige (Runde, Zeit, km/h, Ampel,
  //                                           Gelbe Flagge), gespeichert als MP4/WebM
  //   "Rennen automatisch aufnehmen"          vom Countdown bis kurz nach dem Ziel
  //
  // DIE AUFNAHME LAEUFT UEBER EIN CANVAS und nicht direkt am Kamerastrom: nur so kommen
  // Rundenzeit und Ampel ins Video. Der Kamerastrom selbst wird nie veraendert.
  //
  // ZUSTAND IN EINEM var, und das ist Absicht. 50-drive.js fragt beim Laden ueber
  // cockpitScreenGilt() -> onboardAktiv(), ob der Schirm blaetterbar ist - VOR dieser Datei.
  // Ein let/const hier stuende dann noch in der temporalen Todeszone, und der Lesezugriff
  // braeche die ganze IIFE ab (siehe tools/build.py). Ein var ist schon da, nur leer.
  var onbZ = null;
  function onbZustand() {
    if (!onbZ) {
      onbZ = { stream: null, an: false, fehler: '', rec: null, wache: null,
               zuletzt: 'idle', malTakt: 0, einst: null };
    }
    return onbZ;
  }

  const ONB_STORE = 'omegasim-onboard';
  const ONB_VORGABE = { an: false, quelle: '', quelleName: '', drehen: false,
                        beimStart: true, autoRec: false };
  // Obergrenze einer Aufnahme: der Puffer liegt bis zum Speichern im Speicher des Tablets.
  // 15 min bei 3 Mbit/s sind rund 340 MB - mehr will man einem Tablet nicht zumuten.
  const ONB_MAX_MS = 15 * 60 * 1000;
  const ONB_BITRATE = 3000000;
  // Nach dem Ziel noch so lange weiter aufnehmen (Auslaufen, Zieldurchfahrt im Bild).
  const ONB_NACHLAUF_MS = 3000;

  function onbEinst() {
    const z = onbZustand();
    if (!z.einst) {
      z.einst = Object.assign({}, ONB_VORGABE);
      try {
        const s = JSON.parse(localStorage.getItem(ONB_STORE) || 'null');
        if (s && typeof s === 'object') Object.assign(z.einst, s);
      } catch (e) { /* privat oder kaputt: Vorgabe */ }
    }
    return z.einst;
  }
  function onbSpeichern() {
    try { localStorage.setItem(ONB_STORE, JSON.stringify(onbEinst())); } catch (e) { /* privat */ }
  }

  // Fuer 50-drive.js: den Schirm "Onboard" gibt es nur, solange ein Bild da ist.
  function onboardAktiv() {
    const z = onbZ;
    if (!z || !z.stream) return false;
    const tr = z.stream.getVideoTracks()[0];
    return !!(tr && tr.readyState === 'live');
  }

  function onbStatus(text) {
    const z = onbZustand();
    const s = $('onboard-status');
    if (s) {
      let zeile;
      if (text) zeile = text;
      else if (onboardAktiv()) {
        const tr = z.stream.getVideoTracks()[0];
        const v = $('onboard-video');
        const gr = v && v.videoWidth ? ' · ' + v.videoWidth + '×' + v.videoHeight : '';
        zeile = t('An: {n}').replace('{n}', (tr && tr.label) || t('Kamera')) + gr;
      } else if (z.fehler) zeile = '⚠ ' + z.fehler;
      else zeile = onbEinst().an ? t('Kamera nicht gefunden.') : t('Aus.');
      s.textContent = zeile;
    }
    const b = $('onboard-an');
    if (b) b.textContent = onbEinst().an ? t('Ausschalten') : t('Einschalten');
    const leer = $('onboard-leer');
    if (leer) leer.hidden = onboardAktiv();
  }

  // Die Auswahlliste. Namen gibt der Browser erst heraus, wenn die Kamera einmal erlaubt
  // wurde - vorher steht nur "Standard" drin.
  async function onbQuellenFuellen() {
    const sel = $('onboard-quelle');
    if (!sel || !navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return;
    let geraete = [];
    try { geraete = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === 'videoinput'); }
    catch (e) { return; }
    const e = onbEinst();
    sel.innerHTML = '';
    const std = document.createElement('option');
    std.value = ''; std.textContent = t('Standard');
    sel.appendChild(std);
    geraete.forEach((d, i) => {
      if (!d.deviceId) return;
      const o = document.createElement('option');
      o.value = d.deviceId;
      o.textContent = d.label || (t('Kamera') + ' ' + (i + 1));
      sel.appendChild(o);
    });
    sel.value = [...sel.options].some((o) => o.value === e.quelle) ? e.quelle : '';
  }

  // Die gewaehlte Kamera wiederfinden. Die deviceId bleibt je Seite gleich, solange die
  // Erlaubnis besteht; nach dem Loeschen der Website-Daten aendert sie sich - dann hilft
  // der gemerkte Name (der USB-Empfaenger heisst immer gleich).
  async function onbQuelleSuchen() {
    const e = onbEinst();
    if (!e.quelle && !e.quelleName) return '';
    try {
      const liste = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === 'videoinput');
      if (liste.some((d) => d.deviceId === e.quelle)) return e.quelle;
      const nachName = liste.find((d) => d.label && d.label === e.quelleName);
      if (nachName) return nachName.deviceId;
    } catch (err) { /* dann eben die gemerkte */ }
    return e.quelle;
  }

  function onbStoppen() {
    const z = onbZustand();
    if (z.rec) onbAufnahmeStopp(false);
    if (z.stream) z.stream.getTracks().forEach((tr) => { try { tr.stop(); } catch (e) { /* weg */ } });
    z.stream = null;
    const v = $('onboard-video');
    if (v) v.srcObject = null;
    onbWacheStellen();
    if (typeof cockpitScreenIst === 'function' && cockpitScreenIst().id === 'onboard') cockpitScreenZu('main');
    if (typeof cockpitPunkteMalen === 'function') cockpitPunkteMalen();
    onbStatus();
  }

  async function onbStarten() {
    const z = onbZustand();
    z.fehler = '';
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      z.fehler = t('Dieser Browser kann keine Kamera.');
      onbStatus();
      return false;
    }
    if (z.stream) onbStoppen();
    onbStatus(t('Suche …'));
    const id = await onbQuelleSuchen();
    const video = { width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: 30 } };
    let stream = null;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: id ? Object.assign({ deviceId: { exact: id } }, video) : video, audio: false });
    } catch (err) {
      // Die gemerkte Kamera ist nicht da (Empfaenger abgesteckt): nicht still die Kamera des
      // Tablets nehmen - das Bild zeigte dann den Fahrer statt der Strecke.
      z.fehler = (err && err.name === 'NotAllowedError') ? t('Kamera nicht erlaubt.')
        : (err && (err.name === 'NotFoundError' || err.name === 'OverconstrainedError'))
          ? t('Kamera nicht gefunden.') : ((err && err.message) || String(err));
      log('Onboard-Kamera: ' + z.fehler, 'err');
      onbStatus();
      return false;
    }
    z.stream = stream;
    const tr = stream.getVideoTracks()[0];
    if (tr) {
      const e = onbEinst();
      const st = tr.getSettings ? tr.getSettings() : {};
      if (st.deviceId) { e.quelle = st.deviceId; e.quelleName = tr.label || e.quelleName; onbSpeichern(); }
      tr.addEventListener('ended', () => {
        if (z.stream !== stream) return;
        log('Onboard-Kamera getrennt.', 'err');
        z.fehler = t('Kamera getrennt.');
        onbStoppen();
      });
    }
    const v = $('onboard-video');
    if (v) {
      v.srcObject = stream;
      v.onloadedmetadata = () => onbStatus();
      try { await v.play(); } catch (e) { /* stumm und autoplay: spielt trotzdem */ }
    }
    log('Onboard-Kamera an: ' + ((tr && tr.label) || '?'), 'info');
    onbBildDrehen();
    onbQuellenFuellen();
    onbWacheStellen();
    if (typeof cockpitPunkteMalen === 'function') cockpitPunkteMalen();
    onbStatus();
    return true;
  }

  function onbBildDrehen() {
    const s = $('race-onboardscreen');
    if (s) s.classList.toggle('gedreht', !!onbEinst().drehen);
  }

  // ---- Die Anzeige im Bild ----
  //
  // GELESEN AUS DEM COCKPIT und nicht neu gerechnet: Runde, Zeit und Tempo stehen dort
  // schon, auch wenn der Onboard-Schirm sie verdeckt. Eine zweite Rechnung koennte nur
  // auseinanderlaufen.
  function onbWerte() {
    const txt = (id) => { const el = $(id); return el ? el.textContent.trim() : ''; };
    const lampen = [0, 0, 0, 0, 0];
    const gantry = $('race-gantry');
    const gantryAn = !!(gantry && gantry.classList.contains('on'));
    if (gantryAn) {
      gantry.querySelectorAll('.gantry-lamp[data-col]').forEach((l) => {
        const c = +l.dataset.col - 1;
        if (c < 0 || c > 4) return;
        if (l.classList.contains('red')) lampen[c] = 1;
        else if (l.classList.contains('green') && !lampen[c]) lampen[c] = 2;
      });
    }
    let gelb = false;
    try { gelb = typeof flagState !== 'undefined' && flagState !== 'green'; } catch (e) { /* noch nicht da */ }
    return { runde: txt('race-lap-count') || '0', zeit: txt('race-lap-now') || '–',
             beste: txt('race-lap-best') || '–', kmh: txt('race-speed') || '0',
             gantryAn, lampen, gelb };
  }

  function onbHudMalen() {
    const w = onbWerte();
    const set = (id, v) => { const el = $(id); if (el && el.textContent !== v) el.textContent = v; };
    set('onb-runde', w.runde);
    set('onb-zeit', w.zeit);
    set('onb-kmh', w.kmh);
    const s = $('race-onboardscreen');
    if (s) s.classList.toggle('gelb', w.gelb);
  }

  // Ein Bild in die Aufnahme: Kamera, darueber die Anzeige.
  function onbCanvasMalen(rec) {
    const v = $('onboard-video');
    const c = rec.canvas, g = rec.ctx;
    const W = c.width, H = c.height;
    g.save();
    g.fillStyle = '#000';
    g.fillRect(0, 0, W, H);
    if (v && v.readyState >= 2) {
      if (onbEinst().drehen) { g.translate(W, H); g.rotate(Math.PI); }
      g.drawImage(v, 0, 0, W, H);
    }
    g.restore();
    const w = onbWerte();
    const u = H / 720;   // alles in "Punkten bei 720 Zeilen"
    // Gelbe Flagge: Rahmen ums ganze Bild.
    if (w.gelb) {
      g.lineWidth = 14 * u; g.strokeStyle = '#ffd400';
      g.strokeRect(7 * u, 7 * u, W - 14 * u, H - 14 * u);
    }
    // Leiste unten: Runde, Zeit, km/h.
    const lh = 92 * u;
    const verlauf = g.createLinearGradient(0, H - lh * 1.6, 0, H);
    verlauf.addColorStop(0, 'rgba(0,0,0,0)');
    verlauf.addColorStop(1, 'rgba(0,0,0,.78)');
    g.fillStyle = verlauf;
    g.fillRect(0, H - lh * 1.6, W, lh * 1.6);
    const feld = (x, label, wert, ausr) => {
      g.textAlign = ausr; g.textBaseline = 'alphabetic';
      g.fillStyle = 'rgba(255,255,255,.7)';
      g.font = '600 ' + Math.round(22 * u) + 'px system-ui, sans-serif';
      g.fillText(label, x, H - 70 * u);
      g.fillStyle = '#fff';
      g.font = '800 ' + Math.round(48 * u) + 'px system-ui, sans-serif';
      g.fillText(wert, x, H - 24 * u);
    };
    feld(28 * u, t('Runde').toUpperCase(), w.runde, 'left');
    feld(W / 2, t('Zeit').toUpperCase(), w.zeit, 'center');
    feld(W - 28 * u, 'KM/H', w.kmh, 'right');
    // Ampel oben in der Mitte, solange sie im Cockpit steht.
    if (w.gantryAn) {
      const r = 15 * u, abst = 40 * u, x0 = W / 2 - 2 * abst;
      g.fillStyle = 'rgba(5,7,10,.85)';
      g.fillRect(x0 - 28 * u, 0, 4 * abst + 56 * u, 50 * u);
      for (let i = 0; i < 5; i++) {
        g.beginPath();
        g.arc(x0 + i * abst, 24 * u, r, 0, Math.PI * 2);
        g.fillStyle = w.lampen[i] === 1 ? '#ff2d3a' : w.lampen[i] === 2 ? '#2fe06a' : '#20232b';
        g.fill();
      }
    }
    // Kennung oben rechts, klein.
    g.textAlign = 'right'; g.textBaseline = 'top';
    g.font = '700 ' + Math.round(20 * u) + 'px system-ui, sans-serif';
    g.fillStyle = 'rgba(255,255,255,.55)';
    g.fillText('OmegaSim', W - 22 * u, 18 * u);
  }

  // ---- Aufnahme ----
  function onbMime() {
    if (typeof MediaRecorder === 'undefined') return null;
    // MP4 zuerst: das spielt jedes Handy und jede Schnittsoftware ab (Chrome kann es seit
    // Version 126). Sonst WebM.
    // NUR MIT H.264: ein MP4 mit VP9 drin (das liefert 'video/mp4' allein in Chromium ohne
    // H.264) spielen viele Handys nicht ab - dann lieber ehrlich WebM.
    const kandidaten = ['video/mp4;codecs=avc1.42E01F', 'video/mp4;codecs=avc1',
                        'video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm'];
    for (const k of kandidaten) {
      try { if (MediaRecorder.isTypeSupported(k)) return k; } catch (e) { /* weiter */ }
    }
    return '';
  }

  function onbAufnahmeStart(auto) {
    const z = onbZustand();
    if (z.rec || !onboardAktiv()) return false;
    const mime = onbMime();
    const v = $('onboard-video');
    if (mime === null || !v) { showHudToast(t('Dieser Browser kann nicht aufnehmen.')); return false; }
    const vw = v.videoWidth || 640, vh = v.videoHeight || 480;
    const H = 720, W = Math.round((H * vw / vh) / 2) * 2;
    const canvas = document.createElement('canvas');
    canvas.width = W; canvas.height = H;
    const rec = { canvas, ctx: canvas.getContext('2d'), teile: [], mime: mime || 'video/webm',
                  auto: !!auto, gefahren: false, beginn: Date.now(), stoppTimer: null,
                  verwerfen: false, rekorder: null };
    onbCanvasMalen(rec);
    let strom;
    try {
      strom = canvas.captureStream(30);
      rec.rekorder = new MediaRecorder(strom, mime ? { mimeType: mime, videoBitsPerSecond: ONB_BITRATE }
                                                   : { videoBitsPerSecond: ONB_BITRATE });
    } catch (e) {
      showHudToast(t('Aufnahme ging nicht') + ': ' + e.message);
      return false;
    }
    rec.rekorder.ondataavailable = (ev) => { if (ev.data && ev.data.size) rec.teile.push(ev.data); };
    rec.rekorder.onstop = () => {
      strom.getTracks().forEach((tr) => tr.stop());
      if (rec.verwerfen || !rec.teile.length) { log('Onboard-Aufnahme verworfen.', 'info'); return; }
      const blob = new Blob(rec.teile, { type: rec.mime.split(';')[0] });
      onbVideoSpeichern(blob, rec);
    };
    rec.rekorder.start(1000);
    z.rec = rec;
    log('Onboard-Aufnahme laeuft (' + W + '×' + H + ', ' + (mime || 'Standard') + ').', 'info');
    showHudToast(t('Aufnahme läuft'));
    onbRecKnopf();
    onbWacheStellen();
    return true;
  }

  // speichern=false: verwerfen (abgebrochener Start, Kamera weg vor dem Rennen).
  function onbAufnahmeStopp(speichern) {
    const z = onbZustand();
    const rec = z.rec;
    if (!rec) return;
    z.rec = null;
    clearTimeout(rec.stoppTimer);
    rec.verwerfen = speichern === false && rec.auto && !rec.gefahren;
    try { if (rec.rekorder.state !== 'inactive') rec.rekorder.stop(); } catch (e) { /* schon aus */ }
    onbRecKnopf();
    onbWacheStellen();
  }
  function onbAufnahmeUmschalten() {
    const z = onbZustand();
    if (z.rec) onbAufnahmeStopp(true);
    else onbAufnahmeStart(false);
  }

  function onbRecKnopf() {
    const z = onbZustand();
    const b = $('onboard-rec');
    if (!b) return;
    b.classList.toggle('an', !!z.rec);
    if (z.rec) {
      const s = Math.floor((Date.now() - z.rec.beginn) / 1000);
      b.textContent = '■ ' + Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
    } else {
      b.textContent = '● ' + t('Aufnahme');
    }
  }

  function onbDateiName(rec) {
    const d = new Date(rec.beginn);
    const zz = (n) => String(n).padStart(2, '0');
    const ext = rec.mime.indexOf('mp4') >= 0 ? 'mp4' : 'webm';
    return { name: 'OmegaSim-Onboard-' + d.getFullYear() + '-' + zz(d.getMonth() + 1) + '-' + zz(d.getDate())
                   + '-' + zz(d.getHours()) + zz(d.getMinutes()) + zz(d.getSeconds()), ext };
  }

  function onbBlobBase64(blob) {
    return new Promise((ja, nein) => {
      const r = new FileReader();
      r.onload = () => ja(String(r.result).split(',')[1] || '');
      r.onerror = () => nein(r.error || new Error('lesen'));
      r.readAsDataURL(blob);
    });
  }

  // Speichern. Im Browser als Download; in der Android-App schreibt die App selbst nach
  // Filme/OmegaSim (die WebView laedt keine Blob-Downloads, siehe 60c-streckenbild.js).
  // In Stuecken, damit kein 300-MB-Text auf einmal ueber die Bruecke muss.
  async function onbVideoSpeichern(blob, rec) {
    const { name, ext } = onbDateiName(rec);
    const mb = (blob.size / 1048576).toFixed(1);
    const C = window.Capacitor;
    if (C && C.isNativePlatform && C.isNativePlatform() && C.isPluginAvailable && C.isPluginAvailable('OmegaSicherung')) {
      showHudToast(t('Video wird gespeichert …'));
      try {
        const STUECK = 3 * 1024 * 1024;   // durch 3 teilbar: jedes Stueck ist eigenes Base64
        for (let pos = 0; pos < blob.size; pos += STUECK) {
          const b64 = await onbBlobBase64(blob.slice(pos, pos + STUECK));
          await C.nativePromise('OmegaSicherung', 'videoTeil', { name: name + '.' + ext, base64: b64, erster: pos === 0 });
        }
        const r = await C.nativePromise('OmegaSicherung', 'videoFertig', { name: name + '.' + ext, mime: rec.mime.split(';')[0] });
        showHudToast(t('Video gespeichert') + ': ' + ((r && r.ort) || ''));
        log('Onboard-Video gespeichert: ' + (r && r.ort) + ' (' + mb + ' MB)', 'ok');
      } catch (e) {
        showHudToast(t('Video speichern braucht die neue APK'));
        log('Onboard-Video: ' + ((e && e.message) || e), 'err');
      }
      return;
    }
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = name + '.' + ext;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    showHudToast(t('Video gespeichert'));
    log('Onboard-Video: ' + name + '.' + ext + ' (' + mb + ' MB)', 'ok');
  }

  // ---- Takt: Anzeige, Aufnahme, Rennablauf ----
  //
  // NUR SOLANGE DIE KAMERA AN IST. Ohne Kamera kostet dieses Modul nichts.
  function onbWacheStellen() {
    const z = onbZustand();
    const noetig = onboardAktiv() || !!z.rec;
    if (noetig && !z.wache) {
      z.zuletzt = z.testZustand || ((typeof raceState !== 'undefined') ? raceState : 'idle');
      z.wache = setInterval(() => onbWache(), 250);
      const bild = () => {
        if (!z.wache) { z.malTakt = 0; return; }
        if (z.rec) onbCanvasMalen(z.rec);
        if (typeof cockpitScreenIst === 'function' && cockpitScreenIst().id === 'onboard') onbHudMalen();
        z.malTakt = requestAnimationFrame(bild);
      };
      z.malTakt = requestAnimationFrame(bild);
    } else if (!noetig && z.wache) {
      clearInterval(z.wache); z.wache = null;
      if (z.malTakt) cancelAnimationFrame(z.malTakt);
      z.malTakt = 0;
    }
  }

  // zustandTest: nur fuer den Selbsttest (OMEGA_TEST.onboardWache), sonst raceState.
  function onbWache(zustandTest) {
    const z = onbZustand();
    const e = onbEinst();
    if (z.rec) {
      onbRecKnopf();
      if (Date.now() - z.rec.beginn > ONB_MAX_MS) {
        showHudToast(t('Aufnahme nach 15 min beendet'));
        onbAufnahmeStopp(true);
      }
    }
    // Der Selbsttest gibt den Rennzustand vor, bis er null schickt - sonst saehe der Takt
    // dazwischen das echte 'idle' und braeche die Testaufnahme ab.
    if (zustandTest !== undefined) z.testZustand = zustandTest;
    const jetzt = z.testZustand ? z.testZustand
      : (typeof raceState !== 'undefined') ? raceState : 'idle';
    const vorher = z.zuletzt;
    if (jetzt === vorher) return;
    z.zuletzt = jetzt;
    if (jetzt === 'countdown') {
      if (e.beimStart && onboardAktiv() && typeof cockpitScreenZu === 'function') cockpitScreenZu('onboard');
      if (e.autoRec && !z.rec) onbAufnahmeStart(true);
    }
    if ((jetzt === 'racing' || jetzt === 'finishing') && z.rec) z.rec.gefahren = true;
    if (z.rec && z.rec.auto) {
      if (jetzt === 'finished') {
        const rec = z.rec;
        clearTimeout(rec.stoppTimer);
        rec.stoppTimer = setTimeout(() => { if (z.rec === rec) onbAufnahmeStopp(true); }, ONB_NACHLAUF_MS);
      } else if (jetzt === 'idle') {
        // Abgebrochen. Vor dem Losfahren (Fruehstart, Abbruch im Countdown): verwerfen,
        // es ist kein Rennen drauf. Waehrend des Rennens abgebrochen: behalten.
        onbAufnahmeStopp(z.rec.gefahren);
      }
    }
  }

  // Waehltaste (X) auf dem Onboard-Schirm: Aufnahme an/aus.
  function onboardWaehlen() {
    if (!onboardAktiv()) return false;
    onbAufnahmeUmschalten();
    return true;
  }
  function onboardMalen() { onbHudMalen(); onbRecKnopf(); onbStatus(); }

  // ---- Bedienung in Optionen -> AddOn ----
  if ($('onboard-an')) {
    $('onboard-an').addEventListener('click', async () => {
      const e = onbEinst();
      if (e.an) { e.an = false; onbSpeichern(); onbStoppen(); return; }
      e.an = true; onbSpeichern();
      await onbStarten();
    });
  }
  if ($('onboard-quelle')) {
    $('onboard-quelle').addEventListener('change', (ev) => {
      const e = onbEinst();
      const o = ev.target.selectedOptions[0];
      e.quelle = ev.target.value;
      e.quelleName = ev.target.value && o ? o.textContent : '';
      onbSpeichern();
      if (e.an) onbStarten();
    });
  }
  [['onboard-drehen', 'drehen'], ['onboard-beim-start', 'beimStart'], ['onboard-auto-rec', 'autoRec']]
    .forEach(([id, k]) => {
      const el = $(id);
      if (!el) return;
      el.checked = !!onbEinst()[k];
      el.addEventListener('change', () => {
        onbEinst()[k] = !!el.checked;
        onbSpeichern();
        if (k === 'drehen') onbBildDrehen();
      });
    });
  if ($('onboard-rec')) $('onboard-rec').addEventListener('click', onbAufnahmeUmschalten);

  // Empfaenger wieder eingesteckt: von selbst weiter.
  if (navigator.mediaDevices && navigator.mediaDevices.addEventListener) {
    navigator.mediaDevices.addEventListener('devicechange', () => {
      onbQuellenFuellen();
      if (onbEinst().an && !onboardAktiv()) onbStarten();
    });
  }

  // Beim Laden: war die Kamera an und ist sie schon erlaubt, gleich wieder einschalten -
  // ohne Nachfrage. Sonst wartet sie auf den Knopf (kein Kamera-Dialog beim App-Start).
  (async () => {
    onbBildDrehen();
    onbStatus();
    if (!onbEinst().an || !navigator.mediaDevices) return;
    let erlaubt = false;
    try {
      const p = await navigator.permissions.query({ name: 'camera' });
      erlaubt = p.state === 'granted';
    } catch (e) { /* die App-WebView kennt die Abfrage nicht */ }
    if (erlaubt) { onbStarten(); return; }
    // Nur fuer diese Sitzung aus (nicht gespeichert): der Knopf zeigt "Einschalten".
    onbEinst().an = false;
    onbStatus();
  })();
