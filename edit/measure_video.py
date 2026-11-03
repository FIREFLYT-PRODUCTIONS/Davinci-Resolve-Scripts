"""
FIREFLYT Edit – Schnittrhythmus eines Videos messen
===================================================
Für References: Länge, Schnittzeitpunkte (ffmpeg scdet), Schnitte pro Sekunde,
Schnitte im Hook (0–3 s) und mittlere Einstellungslänge. Nur lokal.

USAGE:
  python measure_video.py "<Video>" ["<Video>" ...] [--json out.json]
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

THRESHOLD = 10      # scdet-Schwelle in Prozent
HOOK = 3.0


def shot_lengths(cuts, duration):
    edges = [0.0] + list(cuts) + [duration]
    return [round(b - a, 3) for a, b in zip(edges, edges[1:])]


def measure(path):
    info = common.probe(path)
    out = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", str(path), "-an", "-vf", f"scale=320:-2,scdet=threshold={THRESHOLD}",
         "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=common.NO_WINDOW,
    )
    cuts = sorted({round(float(t), 3) for t in re.findall(r"lavfi\.scd\.time:\s*([\d.]+)", out.stderr)})
    cuts = [c for c in cuts if 0.05 < c < info["duration"] - 0.05]
    shots = shot_lengths(cuts, info["duration"])
    return {"file": str(path), "duration": round(info["duration"], 2),
            "format": f"{info['width']}x{info['height']}", "cuts": cuts,
            "cuts_per_sec": round(len(cuts) / info["duration"], 2) if info["duration"] else 0,
            "hook_cuts": sum(1 for c in cuts if c < HOOK),
            "avg_shot": round(sum(shots) / len(shots), 2) if shots else 0,
            "shortest": min(shots) if shots else 0, "longest": max(shots) if shots else 0}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="FIREFLYT Schnittrhythmus messen")
    parser.add_argument("videos", nargs="+")
    parser.add_argument("--json")
    args = parser.parse_args()
    results = []
    for video in args.videos:
        info = measure(video)
        results.append(info)
        print(f"{Path(video).name}: {info['duration']}s {info['format']}, {len(info['cuts'])} Schnitte, "
              f"{info['cuts_per_sec']}/s, Hook {info['hook_cuts']}, Einstellung {info['avg_shot']}s "
              f"({info['shortest']}–{info['longest']}s)")
    if args.json:
        common.save_json(args.json, {"videos": results})
    return 0


if __name__ == "__main__":
    sys.exit(main())
