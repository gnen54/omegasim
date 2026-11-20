#!/usr/bin/env python3
"""Opel Manta 400: Motorschleifen aus der sauberen Aufnahme (Freund von Gnen54, 20.11.2026, 7 s,
m4a). Nur im Fork.

Die Aufnahme ist kurz und die Drehzahl steht nirgends lange still. Darum wird jeder Ausschnitt
erst auf eine feste Zuendfrequenz gezogen (Tonhoehe ueber die Zeit glaetten: Zuendfrequenz
messen, Zeitachse so verbiegen, dass sie konstant wird), dann zur Schleife verblendet.
Reihen-4: Zuendrate = Drehzahl / 30.
Aufruf: python3 tools/manta_rec2.py <aufnahme.m4a>
"""
import json, os, subprocess, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import porsche_rec as pr

BASE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
OUT = os.path.join(BASE, 'audio'); WORK = '/tmp/manta_rec2'
# Band: (von s, bis s, Ziel-Zuendfrequenz Hz, Last)
SCHNITTE = {'idle': (0.74, 1.30, 145.0, 1.0), 'mid': (1.86, 2.46, 178.0, 1.0),
            'high': (5.06, 6.12, 228.0, 1.0), 'over': (0.10, 0.56, 122.0, 0.0)}
N, HOP, Z = 4096, 128, 16384


def f0_spur(x, a, b):
    """Zuendfrequenz zwischen a und b (s), HPS mit feinem Raster, leicht geglaettet."""
    SR = pr.SR
    f = np.fft.rfftfreq(Z, 1 / SR); lo, hi = np.searchsorted(f, 60), np.searchsorted(f, 320)
    ts = np.arange(int(a * SR), int(b * SR), HOP); out = []
    for c in ts:
        s = x[max(0, c - N // 2):c + N // 2]
        s = np.pad(s, (0, N - len(s))) * np.hanning(N)
        S = np.log(np.abs(np.fft.rfft(s, Z)) + 1e-9)
        v = [sum(S[int(round(k * h))] for h in range(1, 6)) for k in range(lo, hi)]
        out.append(f[lo + int(np.argmax(v))])
    out = np.array(out)
    k = 9; out = np.convolve(np.pad(out, k // 2, mode='edge'), np.ones(k) / k, mode='valid')
    return ts, out


def glaetten(x, a, b, ziel):
    ts, F = f0_spur(x, a, b)
    i0, i1 = int(a * pr.SR), int(b * pr.SR)
    n = np.arange(i0, i1)
    fn = np.interp(n, ts, F)
    # Phase des Quellsignals in Zuendzyklen; Ausgabe: gleichmaessig 'ziel' Zyklen je Sekunde.
    ph = np.concatenate([[0], np.cumsum(fn[:-1])]) / pr.SR
    m = int(ph[-1] / ziel * pr.SR)
    src = np.interp(np.arange(m) * ziel / pr.SR, ph, n)
    return np.interp(src, np.arange(len(x)), x)


def entrauschen(loop, hz, rest=0.18, breite=4.0):
    """Kammfilter auf der fertigen (periodischen) Schleife: Motor = Vielfache der halben
    Zuendfrequenz (Kurbelwellen-Ordnungen). Alles dazwischen ist Rauschen und wird auf 'rest'
    abgesenkt (nicht ganz weg, sonst klingt es kuenstlich). Gnen54 20.11.: "etwas Entrauschen
    wuerde bestimmt viel bringen"; das Knallen bleibt."""
    S = np.fft.rfft(loop); f = np.fft.rfftfreq(len(loop), 1 / pr.SR)
    g = (hz / 2.0)
    d = np.abs(f / g - np.round(f / g)) * g          # Abstand zur naechsten Ordnung in Hz
    maske = rest + (1 - rest) * np.exp(-0.5 * (d / breite) ** 2)
    maske[f < 40] = 0.0                                # Rumpeln/Wind unter 40 Hz weg
    maske[f > 9000] *= 0.5                             # Zischen oben etwas leiser
    return np.fft.irfft(S * maske, len(loop))


def main(src):
    os.makedirs(WORK, exist_ok=True)
    x = pr.decode(src)
    loops = {}
    for name, (a, b, hz, last) in SCHNITTE.items():
        seg = glaetten(x, a, b, hz)
        loop = entrauschen(pr.circular(seg), hz); loop = loop / (np.max(np.abs(loop)) + 1e-9) * 0.86
        wav = os.path.join(WORK, 'manta400_rec_%s.wav' % name); pr.write_wav(wav, loop)
        ogg = os.path.join(OUT, 'manta400_rec_%s.ogg' % name)
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', wav, '-c:a', 'libvorbis', '-q:a', '4', '-ac', '1', ogg], check=True)
        loops[name] = {'file': os.path.basename(ogg), 'baseRpm': int(round(hz * 30)), 'firingHz': hz,
                       'seconds': round(len(loop) / pr.SR, 4), 'load': last}
        print(name, loops[name], 'Naht', round(pr.seam(loop), 2))
    p = os.path.join(OUT, 'loops.json'); m = json.load(open(p))
    m['manta400_rec'] = {'label': 'Opel Manta 400 (Aufnahme)', 'cylinders': 4,
                         'source': 'Saubere Aufnahme eines Freundes von Gnen54 (20.11.2026), Ausschnitte auf feste '
                                   'Zuendfrequenz geglaettet; nur im Fork gnen54/omegasim',
                         'crackle': 0.55, 'turbo': False, 'idleRpm': 2262, 'limiterRpm': 8000,
                         'loops': loops}
    json.dump(m, open(p, 'w'), indent=1)


if __name__ == '__main__':
    main(sys.argv[1])
