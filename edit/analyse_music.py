"""
FIREFLYT Edit – Musik-Analyse
=============================
Tempo, Beats, Takte (Viertakt, Eins über die stärkste Phase), Abschnitte und
Energie pro Takt mit librosa. Base Edit schneidet die Musik nur auf diesen
Taktgrenzen und legt Schnitte auf die Beats.

USAGE:
  python analyse_music.py "<Musikdatei>" "<Ausgabe.json>"
"""

import argparse
import sys
from pathlib import Path

import librosa
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SR = 22050
HOP = 512
BEATS_PER_BAR = 4


def snap(t, grid):
    return float(min(grid, key=lambda g: abs(g - t)))


def analyse(path):
    y, sr = librosa.load(str(path), sr=SR, mono=True)
    duration = len(y) / sr
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP)
    # trim=False: sonst fehlen leise Intros, genau die braucht der Hook
    _, beat_frames = librosa.beat.beat_track(onset_envelope=onset, sr=sr, hop_length=HOP, trim=False)
    beats = librosa.frames_to_time(beat_frames, sr=sr, hop_length=HOP)
    # Steigung über alle Beats statt Einzelabstand: die Beats liegen auf einem 23-ms-Raster
    tempo = 60.0 / float(np.polyfit(np.arange(len(beats)), beats, 1)[0]) if len(beats) > 1 else 0.0

    # Eins: die Phase, auf der Bass-Energie und Anschlag am stärksten sind
    low = librosa.feature.rms(y=librosa.effects.preemphasis(y, coef=-0.97), hop_length=HOP)[0]
    strength = [onset[f] / (onset.max() or 1) + low[min(f, len(low) - 1)] / (low.max() or 1)
                for f in beat_frames]
    phase = max(range(BEATS_PER_BAR), key=lambda p: float(np.mean(strength[p::BEATS_PER_BAR] or [0])))
    bars = beats[phase::BEATS_PER_BAR]

    # Energie pro Takt und größter Sprung als Drop-Kandidat
    rms = librosa.feature.rms(y=y, hop_length=HOP)[0]
    rms_t = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=HOP)
    edges = list(bars) + [duration]
    energy = [float(rms[(rms_t >= a) & (rms_t < b)].mean()) if np.any((rms_t >= a) & (rms_t < b)) else 0.0
              for a, b in zip(edges[:-1], edges[1:])]
    jumps = [energy[i] - np.mean(energy[max(0, i - 2):i]) if i else 0.0 for i in range(len(energy))]
    drop_bar = int(np.argmax(jumps)) if len(jumps) > 1 else 0

    # Abschnitte: Clustering auf taktsynchronen Klangfarben, Grenzen auf Takte
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=HOP)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, hop_length=HOP, n_mfcc=13)
    bar_frames = librosa.time_to_frames(bars, sr=sr, hop_length=HOP)
    feats = librosa.util.sync(np.vstack([chroma, librosa.util.normalize(mfcc, axis=1)]), bar_frames)
    k = int(np.clip(round(duration / 15), 2, max(2, feats.shape[1] - 1)))
    bounds = librosa.segment.agglomerative(feats, k) if feats.shape[1] > k else np.arange(feats.shape[1])
    starts = sorted({0.0} | {float(bars[min(b, len(bars) - 1)]) for b in bounds if b > 0})
    sections = [{"start": round(s, 3), "end": round(e, 3),
                 "energy": round(float(np.mean([en for b, en in zip(bars, energy) if s <= b < e] or [0])), 4)}
                for s, e in zip(starts, starts[1:] + [duration])]

    return {"file": str(path), "duration": round(duration, 3), "tempo": round(tempo, 2),
            "beats": [round(float(b), 3) for b in beats], "bars": [round(float(b), 3) for b in bars],
            "bar_energy": [round(e, 4) for e in energy], "drop": round(float(bars[drop_bar]), 3),
            "sections": sections}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="FIREFLYT Musik-Analyse")
    parser.add_argument("music")
    parser.add_argument("out")
    args = parser.parse_args()
    info = analyse(args.music)
    common.save_json(args.out, info)
    print(f"{Path(args.music).name}: {info['tempo']} BPM, {len(info['bars'])} Takte, "
          f"{info['duration']:.1f}s, Drop bei {info['drop']:.2f}s")
    for s in info["sections"]:
        print(f"  {s['start']:6.2f} - {s['end']:6.2f}  Energie {s['energy']:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
