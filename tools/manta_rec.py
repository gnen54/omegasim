#!/usr/bin/env python3
"""Opel Manta 400: Motorschleifen aus der Aufnahme des Nutzers (Gnen54, 20.11.2026:
"Best of Opel Manta 400 Michael Gerber - by Rallyeszene.de", MP3). Nur im Fork.

Ausschnitte von Hand nach der Analyse (stetige Zuendfrequenz ueber 1,7 s, Oktavprobe wie in
porsche_rec.py). Reihen-4: Zuendrate = Drehzahl / 30.
Aufruf: python3 tools/manta_rec.py <quelle.mp3>
"""
import json, os, subprocess, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import porsche_rec as pr

BASE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
OUT = os.path.join(BASE, 'audio'); WORK = '/tmp/manta_rec'
LOOP_S = 1.7
# Band: (Startsekunde in der Aufnahme, gemessene Zuendfrequenz Hz, Last)
SCHNITTE = {'idle': (534.6, 75.4, 1.0), 'low': (57.4, 123.8, 1.0), 'mid': (403.2, 236.9, 1.0),
            'high': (305.9, 258.4, 1.0), 'over': (57.4, 123.8, 0.0)}


def main(src):
    os.makedirs(WORK, exist_ok=True)
    x = pr.decode(src)
    loops = {}
    for name, (t, hz, last) in SCHNITTE.items():
        i = int(t * pr.SR); seg = x[i:i + int(LOOP_S * pr.SR)]
        loop = pr.circular(seg); loop = loop / (np.max(np.abs(loop)) + 1e-9) * 0.86
        wav = os.path.join(WORK, 'manta400_rec_%s.wav' % name); pr.write_wav(wav, loop)
        ogg = os.path.join(OUT, 'manta400_rec_%s.ogg' % name)
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', wav, '-c:a', 'libvorbis', '-q:a', '4', '-ac', '1', ogg], check=True)
        loops[name] = {'file': os.path.basename(ogg), 'baseRpm': int(round(hz * 30)), 'firingHz': hz,
                       'seconds': round(len(loop) / pr.SR, 4), 'load': last}
        print(name, loops[name])
    p = os.path.join(OUT, 'loops.json'); m = json.load(open(p))
    m['manta400_rec'] = {'label': 'Opel Manta 400 (Aufnahme)', 'cylinders': 4,
                         'source': 'Aufnahme vom Nutzer (Best of Opel Manta 400 Michael Gerber - by Rallyeszene.de), '
                                   'stetige Ausschnitte; nur im Fork gnen54/omegasim',
                         'crackle': 0.55, 'turbo': False, 'idleRpm': loops['idle']['baseRpm'], 'limiterRpm': 8000,
                         'loops': loops}
    json.dump(m, open(p, 'w'), indent=1)


if __name__ == '__main__':
    main(sys.argv[1])
