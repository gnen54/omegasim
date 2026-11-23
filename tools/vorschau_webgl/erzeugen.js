// Fork (Gnen54, 23.11.2026): Garagen-Vorschaubilder img/autos/<auto>/vorschau.jpg mit WebGL zeichnen.
// Aufruf aus dem Repo-Wurzelverzeichnis:
//   python3 -m http.server 8790 &      (Server im Repo-Wurzelverzeichnis)
//   node tools/vorschau_webgl/erzeugen.js gt3 manta caravelle spider kaefer
// Braucht Playwright mit Chromium (Software-WebGL ueber SwiftShader reicht).
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
(async () => {
  const b = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const p = await b.newPage({ viewport: { width: 1280, height: 720 } });
  p.on('pageerror', (e) => console.log('Fehler:', e.message));
  for (const a of process.argv.slice(2)) {
    await p.goto('http://localhost:8790/tools/vorschau_webgl/render.html');
    const url = await p.evaluate((x) => zeichne(x), a);
    const ziel = path.join('img', 'autos', a, 'vorschau.jpg');
    fs.writeFileSync(ziel, Buffer.from(url.split(',')[1], 'base64'));
    console.log(a, '->', ziel);
  }
  await b.close();
})();
