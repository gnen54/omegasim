  // ============================== FORK GNEN54: VIRTUELLES FAHREN ==============================
  //
  // Alles, was Guenters Fork (gnen54/omegasim, Zweig testversion) am virtuellen Fahren anders oder
  // zusaetzlich hat, steht HIER - nicht verstreut in Luukes 60d-virtuell.js. Diese Datei wird als
  // letzte vor dem Schluss des gemeinsamen Gueltigkeitsbereichs geladen (98z) und
  //   1. traegt zusaetzliche Eintraege in Luukes Listen ein (Boden, Autos, Motoren, Strecken, Kameras),
  //   2. ERSETZT einige Funktionen von Luuke ganz (eine spaetere Funktionsdeklaration mit gleichem Namen
  //      gewinnt im selben Gueltigkeitsbereich) - siehe VF_FORK_ERSETZT; tools/fork_pruefen.py merkt,
  //      wenn Luuke eine davon aendert (Fingerabdruck), damit nichts still verloren geht,
  //   3. liefert die Funktionen fuer die wenigen Einhaengepunkte in 60d-virtuell.js
  //      (Suchbegriff "vfFork" dort: jeder Punkt ist eine Zeile mit typeof-Pruefung).
  // Liste aller Fork-Erweiterungen: FORK-EXTRAS.md im Repo.
  var VF_FORK_ERSETZT = ['vfBodenBau', 'vfBodenGeometrie', 'vfModellDaten', 'vfGrafik', 'vfSpiegelRechtecke', 'vfMotorGewaehlt'];

  // ---- 1. Eintraege in Luukes Listen -------------------------------------------------------
  // Boden "Stein grau marmoriert" (vor dem Rasen einsortiert).
  VF_BOEDEN.splice(Math.max(0, VF_BOEDEN.findIndex((b) => b.id === 'rasen')), 0,
    // BESTELLT (Gnen54, 14.11.2026): ein neutraler Boden ohne Dielen, "nicht komplett eintoenig, so
    // ein bisschen wie marmoriert", nicht schwarz (die Fahrbahn ist schwarz). Eine nahtlos kachelbare
    // Flaeche 120 x 60 cm (Atlas 2048 x 1024), ohne Fugen und ohne Spiegeln/Toenen je Stueck.
    { id: 'stein', name: 'Stein grau marmoriert', art: 'flaeche', breiteCm: 60, laengeCm: 120, spalten: 1, zeilen: 1,
      ton: [[104, 104, 107]], hell: [130, 130, 133], ader: [70, 70, 75], glanz: 0.34 });
  // Porsche 911 GT3 (Freigabe nur muendlich) und Opel Manta B400 (ohne Freigabe): nur im Fork, nie in einen PR.
  Object.assign(VF_MODELL_PFADE, { gt3: 'img/autos/gt3/', manta: 'img/autos/manta/' });
  // Fester Motorklang zu Gnen54s Eigenbauten (die Pfeile in der Garage sind dort gesperrt).
  Object.assign(VF_MOTOR_FEST, { gt3: 'sd_boxer_dunkel', manta: 'manta400_rec' });
  // Freie Strecke Heckenhoim (BESTELLT Gnen54 21.11.): Renn-Rollstrecke 3 x 2 m, nur im Fork.
  VF_FREIE.heckenhoim = { name: 'Heckenhoim', pfad: 'img/strecken/heckenhoim.json' };
  // "Seitennahe Kamera" (Gnen54 16.11.) zwischen naher Verfolgerkamera und Motorhaube.
  VF_KAMERAS.splice(Math.max(0, VF_KAMERAS.findIndex((k) => k.id === 'haube')), 0, { id: 'naeher', name: 'Seitennahe Kamera' });

  // ---- 2. Eigene Funktionen ------------------------------------------------------------------
  // Marmorierter Stein, NAHTLOS kachelbar: periodisches Wertrauschen (Gitter modulo Zellenzahl) in
  // mehreren Oktaven, darauf Adern als |sin| mit ganzzahliger Frequenz je Kachel (auch periodisch),
  // verzerrt vom Rauschen. Zeilen y0..y1 (in Schritten, damit die Garage im Leerlauf rechnen kann).
  function vfSteinRauschen(u, v, n, m, s) {
    const x = u * n, y = v * m, i = Math.floor(x), j = Math.floor(y), fx = x - i, fy = y - j;
    const sx = fx * fx * (3 - 2 * fx), sy = fy * fy * (3 - 2 * fy);
    const g = (a, b) => vfHash(((a % n) + n) % n + s, ((b % m) + m) % m + 7 * s);
    const a0 = g(i, j), a1 = g(i + 1, j), b0 = g(i, j + 1), b1 = g(i + 1, j + 1);
    return (a0 + (a1 - a0) * sx + (b0 - a0 + (b1 - b0 - a1 + a0) * sx) * sy) * 2 - 1;
  }
  function vfSteinTurb(u, v) {
    let t = 0, a = 0.5;
    for (let o = 0, n = 4, m = 2; o < 5; o++, n *= 2, m *= 2, a *= 0.5) t += a * vfSteinRauschen(u, v, n, m, 101 * (o + 1));
    return t;
  }
  function vfSteinZeilen(d, AW, AH, y0, y1, P) {
    const [t0, t1, t2] = P.ton[0], [h0, h1, h2] = P.hell, [a0, a1, a2] = P.ader;
    for (let y = y0; y < y1; y++) {
      const v = y / AH;
      for (let x = 0; x < AW; x++) {
        const u = x / AW, tb = vfSteinTurb(u, v);
        // Grobe Wolken (hell/dunkel) und zwei Adernscharen (Frequenzen ganzzahlig je Kachel).
        const wolke = 0.5 + 0.6 * vfSteinRauschen(u, v, 3, 2, 909) + 0.35 * tb;
        const a1s = Math.abs(Math.sin(Math.PI * (3 * u + 2 * v) + 5.5 * tb));
        const a2s = Math.abs(Math.sin(Math.PI * (5 * u - 3 * v) + 7.0 * vfSteinTurb(v, u)));
        const ader = Math.pow(1 - a1s, 10) * 0.6 + Math.pow(1 - a2s, 14) * 0.35;
        const hw = Math.max(0, Math.min(1, wolke));
        let r = t0 + (h0 - t0) * hw, g = t1 + (h1 - t1) * hw, b = t2 + (h2 - t2) * hw;
        const k = Math.min(1, ader);
        r += (a0 - r) * k; g += (a1 - g) * k; b += (a2 - b) * k;
        const korn = 1 + (vfHash(x, y) - 0.5) * 0.05;
        const i = (y * AW + x) * 4;
        d[i] = r * korn; d[i + 1] = g * korn; d[i + 2] = b * korn;
        d[i + 3] = P.glanz * (0.85 + 0.3 * hw) * 255;
      }
    }
  }
  // ---- GEFAHRENE ZEITEN JE STRECKE (Fork, 19.11., BESTELLT Gnen54: "Gefahrene Zeiten pro Strecke speichern")
  // Je Strecke UND Auto: Bestzeit mit Datum und Zwischenzeiten (fuer das Delta), Rundenzahl und
  // die letzten zehn Runden. Strecke = Name der freien Strecke oder der Code der gebauten Bahn.
  var VF_ZEITEN_STORE = 'omegasim-vf-zeiten';   // var: die Garage kann schon vor dieser Datei zeichnen
  function vfZeitenSchluessel() {
    let s = '-';
    try { s = VF.frei ? 'frei:' + VF.frei.name : 'bahn:' + trackToCode(VF.tiles); } catch (e) { /* ohne */ }
    return s + '|' + vfAutoWahl();
  }
  function vfZeitenAlle() {
    try { return JSON.parse(localStorage.getItem(VF_ZEITEN_STORE || 'omegasim-vf-zeiten') || '{}') || {}; } catch (e) { return {}; }
  }
  function vfZeitenLaden() {
    const e = vfZeitenAlle()[vfZeitenSchluessel()];
    if (e && e.beste > 0) {
      VF.beste = e.beste; VF.besteSplits = Array.isArray(e.splits) ? e.splits : null;
      showHudToast(t('Streckenbestzeit') + ': ' + vfZeitAcc(e.beste, 3));
    }
  }
  function vfZeitMerken(ms, splits) {
    const alle = vfZeitenAlle(), k = vfZeitenSchluessel();
    const e = alle[k] || (alle[k] = { beste: null, datum: null, runden: 0, letzte: [] });
    e.runden += 1;
    e.letzte = [Math.round(ms)].concat(e.letzte || []).slice(0, 10);
    const neu = !(e.beste > 0) || ms < e.beste;
    if (neu) { e.beste = Math.round(ms); e.datum = Date.now(); e.splits = splits || null; }
    try { localStorage.setItem(VF_ZEITEN_STORE || 'omegasim-vf-zeiten', JSON.stringify(alle)); } catch (err) { /* voll */ }
    return neu && e.runden > 1;
  }
  // Bestenliste in der Garage (21.11., BESTELLT Gnen54): je Strecke und Auto die gespeicherte Bestzeit
  // (vfZeitMerken), Rundenzahl und Datum. Zugeklappt, damit die Garage kurz bleibt.
  function vfBestenliste(autos) {
    const box = document.createElement('details');
    box.className = 'vf-bestenliste';
    box.dataset.vf = 'bestenliste';
    const sum = document.createElement('summary');
    sum.textContent = t('Bestzeiten');
    box.appendChild(sum);
    const alle = vfZeitenAlle();
    let jetztBahn = '';
    // Nur lesen: vfTilesWaehlen() setzte ohne Strecke die Ersatzbahn (Nebenwirkung beim blossen Anzeigen der Garage).
    try { if (currentTrackTiles && currentTrackTiles.length >= 3) jetztBahn = trackToCode(currentTrackTiles); } catch (e) { /* ohne */ }
    const zeilen = Object.keys(alle).filter((k) => alle[k] && alle[k].beste > 0).map((k) => {
      const e = alle[k], tr = k.lastIndexOf('|'), ort = k.slice(0, tr), auto = k.slice(tr + 1);
      let strecke = ort;
      if (ort.indexOf('frei:') === 0) strecke = ort.slice(5);
      else if (ort.indexOf('bahn:') === 0) strecke = t('Gebaute Bahn') + (ort.slice(5) === jetztBahn ? ' (' + t('aktuell') + ')' : ' ' + ort.slice(5, 11));
      const a = autos.find((x) => x.v === auto);
      return { strecke, auto: a ? a.name : auto, beste: e.beste, runden: e.runden || 0, datum: e.datum };
    }).sort((x, y) => x.strecke.localeCompare(y.strecke) || x.beste - y.beste);
    if (!zeilen.length) {
      const p = document.createElement('p');
      p.className = 'muted';
      p.textContent = t('Noch keine Bestzeiten');
      box.appendChild(p);
      return box;
    }
    const tab = document.createElement('table');
    tab.className = 'vf-besten-tab';
    tab.style.cssText = 'width:100%;border-collapse:collapse;font-size:0.9em';
    const kopf = tab.insertRow();
    [t('Strecke'), t('Auto'), t('Bestzeit'), t('Runden'), t('Datum')].forEach((h) => {
      const th = document.createElement('th'); th.textContent = h; th.style.textAlign = 'left'; kopf.appendChild(th);
    });
    let spr = 'de';
    try { spr = (typeof lang === 'string' && lang) || 'de'; } catch (e) { /* de */ }
    zeilen.forEach((z) => {
      const r = tab.insertRow();
      [z.strecke, z.auto, vfZeitAcc(z.beste, 3), String(z.runden), z.datum ? new Date(z.datum).toLocaleDateString(spr) : '–']
        .forEach((w) => { const c = r.insertCell(); c.textContent = w; c.style.padding = '2px 6px 2px 0'; });
    });
    box.appendChild(tab);
    return box;
  }
  // 22.11.2026 (BESTELLT Gnen54): auf Handy und Tablet nur Performance - Quality ruckelt dort, und wer es
  // anwaehlt, soll erfahren warum: "Quality nur am PC verfuegbar". Mobil = die App (Capacitor), Android,
  // iPhone/iPad (auch iPadOS, das sich als Macintosh mit Touch meldet). vfMobilErzwungen nur fuer den Selbsttest.
  var vfMobilErzwungen = null;
  function vfMobilGeraet() {
    if (vfMobilErzwungen != null) return vfMobilErzwungen;   // != auch fuer undefined (var vor dem Laden dieser Datei)
    try {
      if (window.Capacitor) return true;
      const ua = navigator.userAgent || '';
      if (/Android|iPhone|iPad|iPod|Mobile/i.test(ua)) return true;
      if (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1) return true;
    } catch (e) { /* unbekannt = PC */ }
    return false;
  }
  function vfForkKameraNaeher(fx, fz, dt, art, D) {
    const nah = false, naeher = true;
    // naeher: Zwischenstufe knapp hinter dem Heck und etwas ueber dem Dach (Auto 9,6 lang, 2,4 hoch) -
    // man sieht die Details des Autos, beim Kreisen auch von der Seite, und noch genug Fahrbahn davor.
    const hinten = naeher ? 6.5 : (nah ? 9 : 15), hoehe = naeher ? 2.8 : (nah ? 3.8 : 8), tau = naeher ? 0.06 : (nah ? 0.08 : 0.15);
    // Gedreht kreist der SOLL-Ort um das Auto; die Nachfuehrung (tau) bleibt dieselbe.
    const zh = naeher ? 1.6 : (nah ? 2.0 : 1.4), vor = naeher ? 7 : (nah ? 8 : 12);
    const k = vfDrehAnwenden({ auge: [VF.x - fx * hinten, hoehe, VF.y - fz * hinten], ziel: [VF.x + fx * vor, zh, VF.y + fz * vor] },
      art, D, VF.x, zh, VF.y);
    if (naeher && D && D.g) {
      // Seitennah: je weiter zur Seite / nach vorn geschwenkt, desto naeher ans Auto (bis 25 % naeher
      // ab 90 Grad) - von schraeg vorn sieht man die Details, von hinten bleibt die Fahrbahn im Blick.
      const g = Math.abs(Math.atan2(Math.sin(D.g), Math.cos(D.g)));
      const f = 1 - 0.25 * Math.min(1, g / (Math.PI / 2));
      k.auge = [VF.x + (k.auge[0] - VF.x) * f, zh + (k.auge[1] - zh) * f, VF.y + (k.auge[2] - VF.y) * f];
    }
    const soll = k.auge;
    const a = 1 - Math.exp(-Math.max(0, dt) / tau);
    VF.kam = VF.kam ? VF.kam.map((q, i) => q + (soll[i] - q) * a) : soll;
    return { auge: VF.kam, ziel: k.ziel, fov: naeher ? 62 : (nah ? 58 : 54), nah: naeher ? 0.3 : 0.5 };
    }
  // Einhaengepunkte in 60d-virtuell.js:
  // Garage: zusaetzliche Autos in Luukes Auswahlliste.
  function vfForkAutos(autos) {
    // Porsche 911 GT3 (Gnen54) auf Vehicle-World-Karosserie (Freigabe nur muendlich) - nur Testversion
    autos.push({ v: 'gt3', name: t('Porsche 911 GT3 (Gnen54, WIP)') });
    // Opel Manta B400 (Gnen54, fuer einen Freund) - KEINE Freigabe: nur im Fork, nie in einen PR
    autos.push({ v: 'manta', name: t('Opel Manta B400 (Gnen54, WIP)') });
  }
  // Garage: Name des festen Motorklangs. sd_boxer_dunkel und manta400_rec stehen nicht immer in der
  // Motorliste - ohne eigenen Namen zeigte die Zeile den globalen Motor (GEMELDET Gnen54 22.11.).
  function vfForkFestName(werte, j) {
    const festNamen = { sd_boxer_dunkel: 'Porsche 911 GT3: Boxer-6, dunkel (Speed Dreams)', manta400_rec: 'Opel Manta 400: Aufnahme (Thorsten)' };
    const fw = werte.find((w) => w.v === vfMotorFest());
    // Eigener Name zuerst: die Menueliste kuerzt "Opel Manta 400: Aufnahme" auf "Opel Manta 400" (wie der gerechnete Motor).
    return festNamen[vfMotorFest()] || (fw ? fw.name : werte[j].name);
  }
  // Garage: Hinweis unter "Grafik" auf Handy/Tablet (dort ist Performance fest, siehe vfGrafik).
  function vfForkGrafikZeile(zeile) {
    if (!vfMobilGeraet()) return;
    const k = document.createElement('small');
    k.textContent = t('Quality nur am PC verfügbar');
    k.style.cssText = 'display:block;opacity:.7;font-weight:400';
    zeile.querySelector('.gk-l').appendChild(k);
  }
  // Garage: unten die Bestenliste je Strecke und Auto.
  function vfForkGarageEnde(rechts, autos) { rechts.appendChild(vfBestenliste(autos)); }
  // Runde an der Linie: Bestzeit je Strecke und Auto dauerhaft merken.
  function vfForkRunde() {
    if (vfZeitMerken(VF.letzte, VF.splits)) showHudToast(t('Neue Streckenbestzeit') + ': ' + vfZeitAcc(VF.letzte, 3));
  }
  // Start der Fahrt: gespeicherte Streckenbestzeit laden (Delta im HUD).
  function vfForkStart() { vfZeitenLaden(); }
  // Glas: sitzt die Kamera IM Auto (Bulli-Onboard hinter der Frontscheibe), nur ein Hauch Toenung -
  // sonst ist das Bild fast schwarz (in Luukes 1.6.22 weggefallen, GEMELDET Gnen54 23.11.).
  function vfForkGlasInnen(auge, x, y, d, s) {
    return !!auge && Math.hypot(auge[0] - x, auge[2] - y) < d.laenge * s * 0.45 && auge[1] < d.hoehe * s;
  }

  // ---- 3. Ersetzte Funktionen von Luuke (Fingerabdruck in tools/fork/fingerabdruecke.json) ----
  // ERSETZT vfBodenBau aus 60d-virtuell.js (Fork-Fassung).
  function* vfBodenBau(P) {
    const AW = VF_ATLAS_B, AH = VF_ATLAS_H, d = new Uint8ClampedArray(AW * AH * 4);
    const rnd = vfZufall(P.id === 'eiche' ? 1911 : P.id === 'grau' ? 2701 : P.id === 'stein' ? 4409 : P.id === 'rasen' ? 5150 : 3307);
    const w = AW / P.spalten, h = AH / P.zeilen, stuecke = [];
    // Fork (Gnen54 14.11.): nahtlose Flaeche "Stein grau marmoriert" (art 'flaeche'), zeilenweise.
    if (P.art === 'flaeche') {
      for (let y = 0; y < AH; y += 64) { vfSteinZeilen(d, AW, AH, y, Math.min(AH, y + 64), P); yield; }
      stuecke.push([0, 0, 1, 1]);
    }
    for (let r = 0; P.art !== 'flaeche' && r < P.zeilen; r++) {
      for (let s = 0; s < P.spalten; s++) {
        if (P.art === 'rasen') yield* vfGrasStueck(d, AW, s * w, r * h, w, h, P, rnd);
        else vfHolzStueck(d, AW, s * w, r * h, w, h, P, rnd);
        stuecke.push([(s * w + 0.5) / AW, (r * h + 0.5) / AH, ((s + 1) * w - 0.5) / AW, ((r + 1) * h - 0.5) / AH]);
        yield;
      }
    }
    let sr = 0, sg = 0, sb = 0, sa = 0;
    for (let i = 0; i < d.length; i += 64) { sr += d[i]; sg += d[i + 1]; sb += d[i + 2]; sa += d[i + 3]; }
    const n = d.length / 64;
    const mittel = [sr / n / 255, sg / n / 255, sb / n / 255];
    d[3] = Math.round(sa / n);
    const texel = [Math.max(1, d[0]) / 255, Math.max(1, d[1]) / 255, Math.max(1, d[2]) / 255];
    vfTexDaten.boden = { d: new Uint8Array(d.buffer), w: AW, h: AH, stuecke, mittel, ferne: [mittel[0] / texel[0], mittel[1] / texel[1], mittel[2] / texel[2]], art: P };
    vfTexDaten.bodenId = P.id;
  }
  // ERSETZT vfBodenGeometrie aus 60d-virtuell.js (Fork-Fassung).
  function vfBodenGeometrie(pts, T, art) {
    const a = [], y = -0.05, cm = TRACK_UNITS_PER_CM;
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    pts.forEach((p) => { minX = Math.min(minX, p.x); maxX = Math.max(maxX, p.x); minY = Math.min(minY, p.y); maxY = Math.max(maxY, p.y); });
    // Fischgraet hat 18-mal so viele Stuecke je Flaeche: dort ein schmalerer Rand (Ecken je Bild).
    const R = art.art === 'fischgraet' ? VF_BODEN_RAND_FG : VF_BODEN_RAND;
    const x0 = minX - R, x1 = maxX + R, z0 = minY - R, z1 = maxY + R;
    const B = art.breiteCm * cm, L = art.laengeCm * cm, rnd = vfZufall(9001 + pts.length);
    const reihen = [];
    let stuecke = 0;
    if (art.art === 'flaeche') {
      // Nahtlose Kacheln im Raster, gleiche Lage und Farbe (sonst saehe man die Kanten).
      const c = [VF_BODEN_HELL, VF_BODEN_HELL, VF_BODEN_HELL];
      for (let z = z0; z < z1; z += B) {
        for (let x = x0; x < x1; x += L) {
          vfViereck(a, [x, y, z, 0, 0], [x + L, y, z, 1, 0], [x + L, y, z + B, 1, 1], [x, y, z + B, 0, 1], c); stuecke++;
        }
      }
    } else if (art.art === 'fischgraet') {
      const r = Math.SQRT1_2, d1 = [r, r], d2 = [-r, r];
      const W = (A, Bb) => [A * d1[0] + Bb * d2[0], A * d1[1] + Bb * d2[1]];
      // Rahmen-Koordinaten der Bodenecken: A = (x + z) r, B = (z - x) r
      const ecken = [[x0, z0], [x1, z0], [x1, z1], [x0, z1]].map(([x, z]) => [(x + z) * r, (z - x) * r]);
      const aMin = Math.min(...ecken.map((e) => e[0])) - L, aMax = Math.max(...ecken.map((e) => e[0])) + L;
      const bMin = Math.min(...ecken.map((e) => e[1])) - L, bMax = Math.max(...ecken.map((e) => e[1])) + L;
      const iMin = Math.floor((aMin + bMin) / (2 * B)), iMax = Math.ceil((aMax + bMax) / (2 * B));
      const jMin = Math.floor((aMin - bMax) / (2 * L)), jMax = Math.ceil((aMax - bMin) / (2 * L));
      const drin = (o, e, q) => { const cx = o[0] + (e[0] * L + q[0] * B) / 2, cz = o[1] + (e[1] * L + q[1] * B) / 2; return cx > x0 - L / 2 && cx < x1 + L / 2 && cz > z0 - L / 2 && cz < z1 + L / 2; };
      for (let j = jMin; j <= jMax; j++) {
        for (let i = iMin; i <= iMax; i++) {
          const oa = i * B + j * L, ob = i * B - j * L;
          const oA = W(oa, ob), oB = W(oa + L, ob + B - L);
          if (drin(oA, d1, d2)) { vfBodenStueck(a, T, rnd, oA, d1, L, d2, B, y); stuecke++; }
          if (drin(oB, d2, d1)) { vfBodenStueck(a, T, rnd, oB, d2, L, d1, B, y); stuecke++; }
        }
      }
    } else {
      let vorher = null;
      for (let z = z0; z < z1; z += B) {
        let ver = rnd() * L;
        for (let k = 0; k < 12 && vorher !== null; k++) {
          const dd = Math.abs(ver - vorher) % L;
          if (Math.min(dd, L - dd) >= L * 0.25) break;
          ver = rnd() * L;
        }
        reihen.push(ver);
        vorher = ver;
        for (let x = x0 - ver; x < x1; x += L) { vfBodenStueck(a, T, rnd, [x, z], [1, 0], L, [0, 1], B, y); stuecke++; }
      }
    }
    // Weite Flaeche ausserhalb der Dielen: vier Streifen bis VF_BODEN_WEIT, Farbe = Mittelwert ueber
    // das Texel (0,0) (konstante Koordinate = immer genau dieses Texel, Alpha dort = mittlerer Glanz).
    const F = VF_BODEN_WEIT, uv = [0.5 / T.w, 0.5 / T.h], c = T.ferne.map((x) => x * VF_BODEN_HELL);
    const streifen = (xa, za, xb, zb) => vfViereck(a, [xa, y, za, uv[0], uv[1]], [xb, y, za, uv[0], uv[1]], [xb, y, zb, uv[0], uv[1]], [xa, y, zb, uv[0], uv[1]], c);
    const xa = x0 - L, xb = x1 + L, za = z0 - L, zb = z1 + L;
    streifen(xa - F, za - F, xb + F, za); streifen(xa - F, zb, xb + F, zb + F);
    streifen(xa - F, za, xa, zb); streifen(xb, za, xb + F, zb);
    return { daten: a, stuecke, reihen, breite: B, laenge: L };
  }
  // ERSETZT vfModellDaten aus 60d-virtuell.js (Fork-Fassung).
  function vfModellDaten(pfad) {
    pfad = pfad || vfModellPfad();
    // 22.11. (GEMELDET Gnen54, Android-Tablet: "furchtbar zu fahren" mit Spider, GT3, Bulli, Manta - ruckelig,
    // nur der Kaefer laeuft): im Grafikmodus Performance die leichte Fassung, die auto.json unter "perf" nennt
    // (tools/modell_perf.py, 0,1 bis 0,3 Mio. statt bis 2 Mio. Dreiecke). Sie bringt NUR die Geometrie
    // (teile, ecken, indizes, indexAb); alles andere bleibt aus auto.json. Quality laedt wie bisher auto.bin.
    const perf = !vfGrafikQual();
    const schl = pfad + (perf ? '|perf' : '');
    if (!vfModellLaden[schl]) {
      // 21.11. (GEMELDET Gnen54, Screenshot: Manta "zerfetzt"): auto.json und auto.bin kamen aus
      // verschiedenen Staenden (Browser-/Pages-Cache) - neue Teileliste auf alter Geometrie. Jetzt erst die
      // json frisch holen, dann die bin mit einer Kennung ihres Inhalts (Ecken/Indizes) als eigene Adresse.
      vfModellLaden[schl] = fetch(pfad + 'auto.json', { cache: 'no-cache' })
        .then((r) => { if (!r.ok) throw new Error('auto.json ' + r.status); return r.json(); })
        .then((meta) => {
          if (!perf || !meta.perf) return [meta, 'auto'];
          // Fehlt die leichte Fassung oder kommt sie nicht, faehrt das Auto eben mit der vollen.
          return fetch(pfad + meta.perf + '.json', { cache: 'no-cache' })
            .then((r) => (r.ok ? r.json() : null))
            .then((g) => (g && g.teile ? [Object.assign({}, meta, { teile: g.teile, ecken: g.ecken, indizes: g.indizes, indexAb: g.indexAb, lod: g.lod }), meta.perf] : [meta, 'auto']))
            .catch(() => [meta, 'auto']);
        })
        .then(([meta, datei]) => fetch(pfad + datei + '.bin?v=' + meta.ecken + '-' + meta.indizes + '-' + meta.indexAb, { cache: 'no-cache' })
          .then((r) => { if (!r.ok) throw new Error(datei + '.bin ' + r.status); return r.arrayBuffer(); })
          .then((bin) => [meta, bin]))
      .then(([meta, bin]) => {
        if (bin.byteLength < meta.indexAb + meta.indizes * 2) throw new Error('auto.bin zu kurz');
        return { meta, ecken: new Float32Array(bin, 0, meta.ecken * 8), indizes: new Uint16Array(bin, meta.indexAb, meta.indizes) };
      }).catch((e) => { vfModellLaden[schl] = null; throw e; });
    }
    return vfModellLaden[schl];
  }
  // ERSETZT vfGrafik aus 60d-virtuell.js (Fork-Fassung).
  function vfGrafik() {
    if (vfMobilGeraet()) return 'perf';   // Fork: Handy/Tablet fest Performance
    try { const v = localStorage.getItem(VF_GRAFIK_STORE); return v === 'perf' ? 'perf' : 'qual'; } catch (e) { return 'qual'; }
  }
  // ERSETZT vfSpiegelRechtecke aus 60d-virtuell.js (Fork-Fassung).
  function vfSpiegelRechtecke(w, h, auto, dpr) {
    if (auto !== 'spider') {
      // Fork (Gnen54, 23.11.: "nicht mehr so hoch"): Groesse wie im Fork bis 22.11. - 30 % der Bildbreite,
      // Hoehe 27 % der Spiegelbreite (Luukes 1.6.22: breiter und nur halb so hoch).
      const sw = Math.round(Math.min(w * 0.3, h * 0.9));
      const sh = Math.round(Math.max(16 * (dpr || 1), sw * 0.27));
      return [{ art: 'innen', q: [Math.round((w - sw) / 2), h - sh, sw, sh] }];
    }
    const sw = Math.round(Math.min(w * 0.17, h * 0.34) * 0.8), sh = Math.round(sw * 0.6);
    const y0 = Math.round(h * 0.15), rand = Math.max(10, Math.round(w * 0.018));
    return [{ art: 'links', q: [rand, y0, sw, sh], sg: 1 }, { art: 'rechts', q: [w - rand - sw, y0, sw, sh], sg: -1 }];
  }
  // ERSETZT vfMotorGewaehlt aus 60d-virtuell.js (Fork-Fassung).
  function vfMotorGewaehlt() {
    if (vfMotorFest()) return vfMotorFest();
    const def = ({ v5r: 'sd_v5r', lynx220: 'sd_lynx', fmcgt4: 'sd_fmc', boxer96: 'sd_boxer', kaefer: 'boxster986', spider: 'listerstorm', caravelle: 'boxster986', gt3: 'sd_boxer_dunkel', manta: 'manta400_rec' })[vfAutoWahl()] || 'sd_v5r';
    try { const v = localStorage.getItem(VF_MOTOR_STORE); return v === null ? def : v; } catch (e) { return def; }
  }

  // ---- 4. Selbsttests des Forks ------------------------------------------------------------------
  // 22.11. (GEMELDET Gnen54: Spider, GT3, Bulli, Manta auf dem Tablet "furchtbar zu fahren"): Performance laedt
  // die leichte Fassung (auto.json "perf"), Quality die volle. Geprueft je Auto: beide laden, die leichte hat
  // deutlich weniger Dreiecke, gueltige Indizes, dieselben Rollen, und Physik/Lichter kommen aus auto.json.
  stAdd('Virtuell: Performance laedt die leichte Fassung (Spider, GT3, Bulli, Manta), Quality die volle', async () => {
    if (location.protocol === 'file:') return { skip: true, mass: 'file://, der Browser verbietet das Laden' };
    const f = [], info = [];
    const merk = localStorage.getItem(VF_GRAFIK_STORE);
    vfMobilErzwungen = false;          // auf dem Handy waere Quality gesperrt - hier geht es um die Dateien
    try {
      for (const a of ['spider', 'gt3', 'caravelle', 'manta']) {
        const pfad = VF_MODELL_PFADE[a];
        localStorage.setItem(VF_GRAFIK_STORE, 'qual');
        const voll = await vfModellDaten(pfad);
        localStorage.setItem(VF_GRAFIK_STORE, 'perf');
        const leicht = await vfModellDaten(pfad);
        const nv = voll.indizes.length / 3, nl = leicht.indizes.length / 3;
        if (!voll.meta.perf) f.push(a + ': auto.json ohne "perf"');
        if (!(nl < nv * 0.6)) f.push(a + ': leicht ' + nl + ' nicht deutlich unter voll ' + nv);
        leicht.meta.teile.forEach((t) => {
          if (t.index0 + t.indizes > leicht.indizes.length) f.push(a + ' ' + t.name + ': Indizes ausserhalb');
          let mx = 0;
          for (let i = t.index0; i < t.index0 + t.indizes; i++) mx = Math.max(mx, leicht.indizes[i]);
          if (mx >= t.ecken) f.push(a + ' ' + t.name + ': Index ' + mx + ' >= ' + t.ecken);
          if (t.ecke0 + t.ecken > leicht.ecken.length / 8) f.push(a + ' ' + t.name + ': Ecken ausserhalb');
        });
        const rollen = (d) => [...new Set(d.meta.teile.map((t) => t.rolle + '/' + (t.achse || '')))].sort().join(',');
        if (rollen(voll) !== rollen(leicht)) f.push(a + ': Rollen verschieden');
        if (JSON.stringify(voll.meta.physik) !== JSON.stringify(leicht.meta.physik)) f.push(a + ': Physik nicht aus auto.json');
        if (JSON.stringify(voll.meta.lichter) !== JSON.stringify(leicht.meta.lichter)) f.push(a + ': Lichter nicht aus auto.json');
        info.push(a + ' ' + Math.round(nv / 1000) + 'k -> ' + Math.round(nl / 1000) + 'k');
      }
    } catch (e) { f.push('Ausnahme: ' + e.message); }
    finally { vfMobilErzwungen = null; if (merk === null) localStorage.removeItem(VF_GRAFIK_STORE); else localStorage.setItem(VF_GRAFIK_STORE, merk); }
    return { ok: !f.length, mass: f.length ? f.join(' | ') : info.join(', ') };
  });

  // 22.11. (BESTELLT Gnen54): auf Handy/Tablet nur Performance, Quality mit Hinweis "nur am PC".
  stAdd('Virtuell: auf Handy und Tablet nur Performance, am PC Quality waehlbar', () => {
    const f = [];
    const merk = localStorage.getItem(VF_GRAFIK_STORE);
    try {
      localStorage.setItem(VF_GRAFIK_STORE, 'qual');
      vfMobilErzwungen = true;
      if (vfGrafik() !== 'perf') f.push('mobil trotz gespeichertem Quality nicht Performance');
      if (vfGrafikQual()) f.push('mobil vfGrafikQual() wahr');
      vfMobilErzwungen = false;
      if (vfGrafik() !== 'qual') f.push('am PC wird Quality nicht uebernommen');
      if (t('Quality nur am PC verfügbar') === '') f.push('Hinweistext leer');
    } finally { vfMobilErzwungen = null; if (merk === null) localStorage.removeItem(VF_GRAFIK_STORE); else localStorage.setItem(VF_GRAFIK_STORE, merk); }
    return { ok: !f.length, mass: f.length ? f.join(' | ') : 'mobil Performance fest, PC frei; dieses Geraet: ' + (vfMobilGeraet() ? 'mobil' : 'PC') };
  });

  // Luukes Spiegeltest verlangt einen flachen Streifen (hoechstens 10 bzw. 12 % der Bildhoehe). Der Fork hat
  // bewusst den hoeheren Spiegel (27 % der Spiegelbreite, BESTELLT Gnen54 23.11.). Sein Test bleibt unveraendert
  // in 95-selftest.js; hier werden NUR die beiden Hoehen-Meldungen durch die Fork-Pruefung ersetzt, alle anderen
  // Pruefungen (oben am Rand, mittig, Spider, Verfolgerkamera) zaehlen wie bei Luuke.
  {
    const st = ST_TESTS.find((x) => x.name.indexOf('Rueckspiegel nur als schmaler Streifen') >= 0);
    if (st) {
      const orig = st.fn;
      st.name += ' [Fork: Spiegelhoehe wie im Fork]';
      st.fn = async () => {
        const r = await orig();
        if (!r || r.skip || r.ok) return r;
        const hoch = /^(Innenspiegel \d+ px hoch \(kein schmaler Streifen\)|Spiegel \d+ px hoch)$/;
        const rest = String(r.mass).split(' | ').filter((m) => !hoch.test(m));
        const q = vfSpiegelRechtecke(1280, 720, 'v5r', 1)[0].q;
        if (Math.abs(q[3] - Math.round(q[2] * 0.27)) > 1) rest.push('Innenspiegel nicht in Fork-Groesse: ' + q[2] + ' x ' + q[3]);
        return { ok: !rest.length, mass: rest.length ? rest.join(' | ') : 'Fork-Groesse ' + q[2] + ' x ' + q[3] + ' px (bei 1280 x 720), sonst wie Luuke' };
      };
    }
  }
