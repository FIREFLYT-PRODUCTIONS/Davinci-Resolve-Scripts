"""
FIREFLYT Edit – Technik-Durchlauf der Takes
===========================================
Misst alle 0,25 s Schärfe, Wackler, Reißschwenks und Belichtung, jeweils relativ
zum Take (Log-Material ist flach). Ergebnis sind die technisch sauberen Abschnitte
und Kontaktbilder, aus denen Claude die Selects wählt. Liest die Proxys, sonst
die Originale. Nur lokal, nichts verlässt den Rechner.

USAGE:
  python analyse_takes.py "<Projektordner>" [--editor FELIX] [--only 4824 4825]

Ergebnis: 00 - <EDITOR>\\CLAUDE\\SELECTS\\takes.json und SELECTS\\sheets\\sheet_NNN.jpg
"""

import argparse
import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

STEP = 0.25            # Sekunden pro Messung
WIDTH = 320            # Messbreite in Pixel
MIN_CLEAN = 2.0        # kürzester brauchbarer Abschnitt
BLUR_TAKE = 0.35       # Schärfe unter 35 % des schärfsten Zehntels im Take
BLUR_GLOBAL = 0.15     # oder unter 15 % des Projekt-Medians
SHAKE = 0.02           # unruhige Verschiebung, Anteil der Bildbreite pro Messung
WHIP = 0.12            # Verschiebung, ab der es ein Reißschwenk ist
DARK, BRIGHT = 0.45, 1.8
CLIPPED = 0.25         # Anteil ausgebrannter Pixel
TILE_H = 240
TILES = 6
TAKES_PER_SHEET = 4
WORKERS = 4


# ─────────────────────────────────────────────
#  MESSEN (rein, testbar)
# ─────────────────────────────────────────────

def measure_frames(frames):
    """frames: Graustufenbilder gleicher Größe. Liefert pro Bild die Messwerte."""
    window = None
    samples, prev = [], None
    for frame in frames:
        f = frame.astype(np.float32)
        if window is None:
            window = cv2.createHanningWindow((f.shape[1], f.shape[0]), cv2.CV_32F)
        sample = {
            "sharp": float(cv2.Laplacian(f, cv2.CV_32F).var()),
            "mean": float(f.mean()),
            "clip": float((frame >= 250).mean()),
            "shift": (0.0, 0.0), "response": 1.0, "mad": 0.0,
        }
        if prev is not None:
            (dx, dy), response = cv2.phaseCorrelate(prev, f, window)
            sample["shift"] = (float(dx), float(dy))
            sample["response"] = float(response)
            sample["mad"] = float(np.abs(f - prev).mean())
        samples.append(sample)
        prev = f
    width = frames[0].shape[1] if frames else WIDTH
    for s in samples:
        s["width"] = width
    return samples


def classify(samples, global_sharp):
    """Pro Messung None (sauber) oder der Grund: unscharf, wackelig, Reissschwenk, Belichtung."""
    if not samples:
        return []
    sharp = np.array([s["sharp"] for s in samples])
    p90 = float(np.percentile(sharp, 90))
    mean_med = float(np.median([s["mean"] for s in samples])) or 1.0
    shifts = np.array([s["shift"] for s in samples])
    width = samples[0]["width"]
    flags = []
    for i, s in enumerate(samples):
        lo, hi = max(1, i - 2), min(len(samples), i + 3)
        trend = np.median(shifts[lo:hi], axis=0) if hi > lo else np.zeros(2)
        jitter = float(np.hypot(*(shifts[i] - trend))) if i else 0.0
        speed = float(np.hypot(*shifts[i]))
        if i and (speed > WHIP * width or (s["response"] < 0.03 and s["mad"] > 25)):
            flags.append("Reissschwenk")
        elif s["mean"] < 10 or s["mean"] < DARK * mean_med or s["mean"] > BRIGHT * mean_med \
                or s["clip"] > CLIPPED:
            flags.append("Belichtung")
        elif s["sharp"] < BLUR_TAKE * p90 or s["sharp"] < BLUR_GLOBAL * global_sharp:
            flags.append("unscharf")
        elif jitter > SHAKE * width:
            flags.append("wackelig")
        else:
            flags.append(None)
    # Ein Wackler wirkt auf die Messung davor mit, beide fliegen raus
    for i in range(1, len(flags)):
        if flags[i] == "wackelig" and flags[i - 1] is None:
            flags[i - 1] = "wackelig"
    return flags


def segments(flags, step=STEP, min_len=MIN_CLEAN):
    """Saubere Abschnitte [start, ende] in Sekunden und verworfene Bereiche mit Grund."""
    clean, rejected = [], []
    i = 0
    while i < len(flags):
        j = i
        while j < len(flags) and (flags[j] is None) == (flags[i] is None):
            j += 1
        start, end = round(i * step, 3), round(j * step, 3)
        if flags[i] is None:
            if end - start >= min_len:
                clean.append([start, end])
            else:
                rejected.append({"from": start, "to": end, "why": "zu kurz"})
        else:
            why = Counter(flags[i:j]).most_common(1)[0][0]
            rejected.append({"from": start, "to": end, "why": why})
        i = j
    return clean, rejected


def tile_times(clean, max_tiles=TILES):
    """Bildzeitpunkte für das Kontaktbild: verteilt nach Länge, mindestens eins pro Abschnitt."""
    if not clean:
        return []
    parts = sorted(clean, key=lambda c: c[1] - c[0], reverse=True)[:max_tiles]
    total = sum(e - s for s, e in parts)
    counts = [1] * len(parts)
    for _ in range(max_tiles - len(parts)):
        k = max(range(len(parts)), key=lambda n: (parts[n][1] - parts[n][0]) / total - counts[n] / max_tiles)
        counts[k] += 1
    times = []
    for (s, e), n in zip(parts, counts):
        times += [round(s + (e - s) * (k + 0.5) / n, 2) for k in range(n)]
    return sorted(times)


# ─────────────────────────────────────────────
#  DATEIEN
# ─────────────────────────────────────────────

def scaled_size(width, height, target=WIDTH):
    return target, int(round(target * height / width / 2) * 2)


def decode_gray(path, width, height):
    w, h = scaled_size(width, height)
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-an",
         "-vf", f"fps={1 / STEP:g},scale={w}:{h},format=gray", "-f", "rawvideo", "-"],
        capture_output=True, creationflags=common.NO_WINDOW,
    )
    data = np.frombuffer(out.stdout, np.uint8)
    n = data.size // (w * h)
    return [data[k * w * h:(k + 1) * w * h].reshape(h, w) for k in range(n)]


def grab_tile(path, t, width, height):
    tw = int(round(TILE_H * width / height))
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(path), "-frames:v", "1", "-an",
         "-vf", f"scale={tw}:{TILE_H}", "-pix_fmt", "bgr24", "-f", "rawvideo", "-"],
        capture_output=True, creationflags=common.NO_WINDOW,
    )
    data = np.frombuffer(out.stdout, np.uint8)
    if data.size < tw * TILE_H * 3:
        return np.zeros((TILE_H, tw, 3), np.uint8)
    return data[:tw * TILE_H * 3].reshape(TILE_H, tw, 3)


def measure_take(take):
    read = take["proxy"] or take["file"]
    info = common.probe(read)
    frames = decode_gray(read, info["width"], info["height"])
    take["read_size"] = [info["width"], info["height"]]
    return measure_frames(frames)


def build_sheets(takes, sheet_dir, log):
    """Pro Bild bis zu 4 Takes, je Take eine Zeile mit Key, Kamera und beschrifteten Bildern."""
    sheet_dir.mkdir(parents=True, exist_ok=True)
    for old in sheet_dir.glob("sheet_*.jpg"):
        old.unlink()
    rows_takes = [t for t in takes if t["clean"]]

    def row(take):
        read = take["proxy"] or take["file"]
        w, h = take["read_size"]
        label = np.full((TILE_H, 200, 3), 30, np.uint8)
        lines = [take["key"], Path(take["file"]).parent.name[:16], Path(take["file"]).stem[-14:],
                 f"{take['duration']:.1f}s, {take['fps']:.2f}fps"]
        for n, text in enumerate(lines):
            cv2.putText(label, text, (8, 40 + 42 * n), cv2.FONT_HERSHEY_SIMPLEX,
                        0.85 if n == 0 else 0.55, (255, 255, 255), 2 if n == 0 else 1, cv2.LINE_AA)
        tiles = [label]
        for t in take["tiles"]:
            tile = grab_tile(read, t, w, h).copy()
            cv2.rectangle(tile, (0, TILE_H - 30), (tile.shape[1], TILE_H), (0, 0, 0), -1)
            cv2.putText(tile, f"{take['key']} {t:.1f}s", (6, TILE_H - 9), cv2.FONT_HERSHEY_SIMPLEX,
                        0.6, (0, 255, 255), 1, cv2.LINE_AA)
            tiles += [tile, np.zeros((TILE_H, 4, 3), np.uint8)]
        return np.hstack(tiles)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        rows = list(pool.map(row, rows_takes))
    for n in range(0, len(rows), TAKES_PER_SHEET):
        chunk = rows[n:n + TAKES_PER_SHEET]
        width = max(r.shape[1] for r in chunk)
        padded = [np.hstack([r, np.zeros((TILE_H, width - r.shape[1], 3), np.uint8)]) for r in chunk]
        gap = np.full((6, width, 3), 80, np.uint8)
        sheet = np.vstack([x for r in padded for x in (r, gap)])
        name = f"sheet_{n // TAKES_PER_SHEET + 1:03d}.jpg"
        cv2.imwrite(str(sheet_dir / name), sheet, [cv2.IMWRITE_JPEG_QUALITY, 82])
        for take in rows_takes[n:n + TAKES_PER_SHEET]:
            take["sheet"] = name
    log(f"  {len(rows)} Takes auf {(len(rows) + TAKES_PER_SHEET - 1) // TAKES_PER_SHEET} Kontaktbildern")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="FIREFLYT Technik-Durchlauf der Takes")
    parser.add_argument("folder")
    parser.add_argument("--editor", default="CONRAD")
    parser.add_argument("--only", nargs="*", help="nur Dateien, deren Name einen dieser Teile enthält")
    args = parser.parse_args()

    log = common.Log("ANALYSE_TAKES")
    root = common.claude_dir(args.folder, args.editor)
    started = time.time()
    videos = common.source_videos(args.folder)
    if args.only:
        videos = [v for v in videos if any(o.lower() in v.name.lower() for o in args.only)]
    takes, broken = [], []
    for n, path in enumerate(videos, 1):
        info = common.probe(path)
        if not info["width"] or not info["duration"]:
            broken.append(path.name)
            continue
        takes.append({"key": f"T{n:03d}", "file": str(path),
                      "proxy": str(common.proxy_for(path)) if common.proxy_for(path) else None,
                      "fps": info["fps"], "frames": info["frames"], "width": info["width"],
                      "height": info["height"], "duration": round(info["duration"], 3),
                      "has_audio": info["has_audio"]})
    log(f"{len(takes)} Takes, {sum(1 for t in takes if t['proxy'])} mit Proxy, {len(broken)} defekt")

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        all_samples = list(pool.map(measure_take, takes))
    global_sharp = float(np.median([s["sharp"] for samples in all_samples for s in samples] or [1]))
    for take, samples in zip(takes, all_samples):
        take["clean"], take["rejected"] = segments(classify(samples, global_sharp))
        take["tiles"] = tile_times(take["clean"])
        take["sheet"] = None
    log(f"  Messung fertig nach {time.time() - started:.0f}s")

    build_sheets(takes, root / "SELECTS" / "sheets", log)
    usable = sum(t["clean"][i][1] - t["clean"][i][0] for t in takes for i in range(len(t["clean"])))
    total = sum(t["duration"] for t in takes)
    empty = [Path(t["file"]).name for t in takes if not t["clean"]]
    common.save_json(root / "SELECTS" / "takes.json",
                     {"project": Path(args.folder).name, "step": STEP, "takes": takes, "broken": broken})
    log(f"Sauber: {usable / 60:.1f} von {total / 60:.1f} Min. ({usable / max(total, 1):.0%})")
    if empty:
        log(f"Ohne sauberen Abschnitt ({len(empty)}): {', '.join(empty)}")
    if broken:
        log(f"Defekt, nicht lesbar ({len(broken)}): {', '.join(broken)}")
    log(f"Fertig nach {time.time() - started:.0f}s: {root / 'SELECTS' / 'takes.json'}")
    log.write(root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
