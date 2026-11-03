"""
FIREFLYT Edit – gemeinsame Hilfen ohne Resolve
==============================================
Pfade der Claude-Ablage, JSON, Framemathematik und ffprobe. Wird von allen
Skripten unter edit\\ genutzt.
"""

import json
import subprocess
from datetime import datetime
from pathlib import Path

SCRIPS_DIR = Path(__file__).resolve().parents[1]
CLAUDE_SUBDIRS = ("SELECTS", "EDIT", "SOUND", "LOGS")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def claude_dir(project_dir, editor="CONRAD"):
    """<Projekt>\\00 - <EDITOR>\\CLAUDE, beim ersten Gebrauch mit Unterordnern angelegt."""
    root = Path(project_dir) / f"00 - {editor.upper()}" / "CLAUDE"
    for sub in CLAUDE_SUBDIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class Log:
    """Schreibt auf den Bildschirm und am Ende nach CLAUDE\\LOGS."""

    def __init__(self, name):
        self.name = name
        self.lines = []

    def __call__(self, msg=""):
        line = f"[{datetime.now():%H:%M:%S}] {msg}" if msg else ""
        print(line, flush=True)
        self.lines.append(line)

    def write(self, root):
        target = Path(root) / "LOGS" / f"{self.name}_{datetime.now():%Y%m%d_%H%M%S}.log"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(self.lines), encoding="utf-8")
        return target


def src_to_record(item_start, item_src_start, src_frame, tl_fps, clip_fps):
    """Timeline-Frame einer Quell-Stelle. Clips mit anderer Framerate laufen in Echtzeit."""
    return item_start + round((src_frame - item_src_start) * float(tl_fps) / float(clip_fps))


def seconds_to_frames(sec, fps):
    return round(sec * float(fps))


def fps_value(text):
    """'60000/1001' oder '23.976' -> float."""
    text = str(text)
    if "/" in text:
        num, den = text.split("/")
        return float(num) / float(den) if float(den) else 0.0
    return float(text)


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,width,height,r_frame_rate,nb_frames:stream_side_data=rotation:format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True, creationflags=NO_WINDOW,
    )
    data = json.loads(out.stdout or "{}")
    info = {"fps": None, "frames": None, "width": None, "height": None,
            "duration": float(data.get("format", {}).get("duration") or 0), "has_audio": False}
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video" and info["width"] is None:
            info["width"], info["height"] = stream.get("width"), stream.get("height")
            # Hochkant-Clips der Sony liegen quer mit Drehung 90 in der Datei, ffmpeg dreht beim Lesen
            rotation = next((abs(int(s.get("rotation", 0))) for s in stream.get("side_data_list", [])
                             if "rotation" in s), 0)
            if rotation in (90, 270):
                info["width"], info["height"] = info["height"], info["width"]
            info["fps"] = fps_value(stream.get("r_frame_rate", "0/1"))
            frames = stream.get("nb_frames")
            info["frames"] = int(frames) if frames and frames.isdigit() else round(info["duration"] * info["fps"])
        elif stream.get("codec_type") == "audio":
            info["has_audio"] = True
    return info


def proxy_for(path):
    """Proxy des Blackmagic Proxy Generators: <Ordner>\\Proxy\\<Name>.mov"""
    path = Path(path)
    candidate = path.parent / "Proxy" / f"{path.stem}.mov"
    return candidate if candidate.exists() else None


def source_videos(project_dir, exts=(".mp4", ".mov", ".mxf")):
    """Alle Videos unter 01 - SOURCE\\VIDEOS, ohne Proxy-Ordner."""
    root = Path(project_dir) / "01 - SOURCE" / "VIDEOS"
    return sorted(p for p in root.rglob("*")
                  if p.suffix.lower() in exts and "proxy" not in (s.lower() for s in p.parts))
