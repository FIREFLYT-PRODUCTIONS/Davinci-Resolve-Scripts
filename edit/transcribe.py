"""
FIREFLYT Edit – Transkript der Takes
====================================
Lokal mit faster_whisper auf der GPU, mit Wortzeiten. Damit liegen Selects und
Schnitte bei Sprache an Satzgrenzen. Nichts wird hochgeladen.

USAGE:
  python transcribe.py "<Projektordner>" [--editor FELIX] [--model large-v3-turbo] [--language de]

Liest SELECTS\\takes.json (erst analyse_takes.py), schreibt SELECTS\\transcripts.json.
Takes, die schon ein Transkript haben, werden übersprungen.
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

MIN_WORDS = 5
MAX_NO_SPEECH = 0.5


def add_cuda_dlls():
    """cuBLAS und cuDNN kommen als pip-Pakete (nvidia-*-cu12), Windows findet deren DLLs sonst nicht."""
    import importlib.util
    spec = importlib.util.find_spec("nvidia")
    for base in (spec.submodule_search_locations if spec else []):
        for bin_dir in Path(base).glob("*/bin"):
            os.add_dll_directory(str(bin_dir))
            os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")


def load_audio(path, sr=16000):
    """Mono 16 kHz per ffmpeg. faster_whisper selbst nutzt PyAV, das in dieser Version nicht passt."""
    out = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(sr),
                          "-f", "f32le", "-"], capture_output=True, creationflags=common.NO_WINDOW)
    return np.frombuffer(out.stdout, np.float32)


def speech_segments(segments):
    """Behält Segmente, die wirklich Sprache sind. Rein, testbar."""
    kept = []
    for seg in segments:
        if seg["no_speech"] >= MAX_NO_SPEECH or not seg["text"].strip():
            continue
        kept.append(seg)
    words = sum(len(s["words"]) for s in kept)
    return kept if words >= MIN_WORDS else []


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="FIREFLYT Transkript der Takes")
    parser.add_argument("folder")
    parser.add_argument("--editor", default="CONRAD")
    parser.add_argument("--model", default="large-v3-turbo")
    parser.add_argument("--language", default="de")
    args = parser.parse_args()

    log = common.Log("TRANSCRIBE")
    root = common.claude_dir(args.folder, args.editor)
    takes = common.load_json(root / "SELECTS" / "takes.json")["takes"]
    target = root / "SELECTS" / "transcripts.json"
    done = common.load_json(target)["takes"] if target.exists() else {}

    add_cuda_dlls()
    from faster_whisper import WhisperModel
    started = time.time()
    model = WhisperModel(args.model, device="cuda", compute_type="float16")
    todo = [t for t in takes if t.get("has_audio") and t["file"] not in done]
    log(f"{len(todo)} Takes zu transkribieren, {len(done)} schon fertig")
    for n, take in enumerate(todo, 1):
        source = take["proxy"] or take["file"]
        audio = load_audio(source)
        if audio.size < 16000:
            done[take["file"]] = {"key": take["key"], "speech": False, "segments": []}
            continue
        raw, _ = model.transcribe(audio, language=args.language, vad_filter=True,
                                  word_timestamps=True, condition_on_previous_text=False)
        segments = [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip(),
                     "no_speech": round(s.no_speech_prob, 3),
                     "words": [[round(w.start, 2), round(w.end, 2), w.word.strip()] for w in (s.words or [])]}
                    for s in raw]
        kept = speech_segments(segments)
        done[take["file"]] = {"key": take["key"], "speech": bool(kept), "segments": kept}
        if kept:
            log(f"  {take['key']} {Path(take['file']).name}: {' '.join(s['text'] for s in kept)[:120]}")
        if n % 10 == 0:
            common.save_json(target, {"model": args.model, "takes": done})
    common.save_json(target, {"model": args.model, "takes": done})
    speech = sum(1 for v in done.values() if v["speech"])
    log(f"Fertig nach {time.time() - started:.0f}s: {speech} von {len(done)} Takes mit Sprache")
    log.write(root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
