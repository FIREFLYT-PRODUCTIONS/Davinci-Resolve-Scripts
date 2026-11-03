"""
FIREFLYT Edit – Sound Design auf eine Kopie legen
=================================================
Liest SOUND\\vNN.json und legt Effekte und Atmo auf eine Kopie der Version:
<Projekt>_vNN_SD mit Audiospuren SFX (SFX 2 ...) und ATMO. Die Version selbst
bleibt unverändert. Alle Clips bekommen denselben festen, leisen Pegel; Mix und
Ducking macht der Editor.

Quellen: Originalton der Kamera (Take-MP4, Bereich per "in"/"dur"), Artlist-SFX
und lizenzfreie Effekte. Effekt-Dateien liegen unter 00 - <EDITOR>\\ASSETS\\SOUND_FX, in Resolve im Bin
01 - ASSETS\\SOUND_FX.

USAGE:
  python place_sound.py "<Projektordner>" v01 [--editor FELIX] [--check]
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SFX_BIN = ("01 - ASSETS", "SOUND_FX")
TRACK_RE = re.compile(r"^(SFX( \d+)?|ATMO( \d+)?)$")
MAX_LEVEL = -6


def track_names(sound):
    names = {i["track"] for i in sound["items"]}
    return sorted(names, key=lambda n: (not n.startswith("SFX"), n))


def validate_sound(sound, length):
    problems = []
    level = sound.get("level_db")
    if level is None or level > MAX_LEVEL:
        problems.append(f"Pegel fehlt oder ist zu laut (Vorgabe: fest und leise, hoechstens {MAX_LEVEL} dB)")
    by_track = {}
    for i in sound["items"]:
        if not TRACK_RE.match(i["track"]):
            problems.append(f"Spur '{i['track']}' ist keine SFX- oder ATMO-Spur")
        if i["at"] < 0 or i["at"] + i["dur"] > length + 0.01:
            problems.append(f"{Path(i['file']).name} bei {i['at']:.2f}s liegt ausserhalb der Timeline")
        by_track.setdefault(i["track"], []).append(i)
    for track, items in by_track.items():
        items.sort(key=lambda i: i["at"])
        for a, b in zip(items, items[1:]):
            if b["at"] < a["at"] + a["dur"] - 0.001:
                problems.append(f"{track}: {Path(b['file']).name} bei {b['at']:.2f}s ueberlappt den Clip davor")
    return problems


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="FIREFLYT Sound Design auf Kopie")
    parser.add_argument("folder")
    parser.add_argument("version")
    parser.add_argument("--editor", default="CONRAD")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    log = common.Log(f"PLACE_SOUND_{args.version}")
    root = common.claude_dir(args.folder, args.editor)
    sound = common.load_json(root / "SOUND" / f"{args.version}.json")
    edit = common.load_json(root / "EDIT" / f"{args.version}.json")
    music = edit["music"]["segments"]
    length = sum(e - s for s, e in music)
    problems = validate_sound(sound, length)
    for i in sound["items"]:
        if not Path(i["file"]).exists():
            problems.append(f"Datei fehlt: {i['file']}")
    for p in problems:
        log(f"! {p}")
    if problems:
        log("ABBRUCH: Sound-Liste ist nicht in Ordnung.")
        log.write(root)
        return 2
    log("Sound-Liste geprueft: in Ordnung")
    if args.check:
        return 0

    import build_edit as be
    import resolve_util as ru
    try:
        resolve, pm, project = ru.open_project(args.folder, args.editor)
    except ru.EditError as error:
        log(f"ABBRUCH: {error}")
        log.write(root)
        return 2
    by_name = ru.timelines(project)
    base = f"{project.GetName()}_{args.version}"
    name = f"{base}_SD"
    if base not in by_name:
        log(f"ABBRUCH: Version '{base}' fehlt. Erst Base Edit.")
        log.write(root)
        return 2
    if name in by_name:
        log(f"ABBRUCH: '{name}' gibt es schon. Eine vorhandene Kopie wird nie veraendert.")
        log.write(root)
        return 4

    project.SetCurrentTimeline(by_name[base])
    timeline = by_name[base].DuplicateTimeline(name)
    if not timeline:
        log("ABBRUCH: Kopie liess sich nicht anlegen.")
        log.write(root)
        return 2
    project.SetCurrentTimeline(timeline)
    fps = float(timeline.GetSetting("timelineFrameRate"))
    start = timeline.GetStartFrame()
    media_pool = project.GetMediaPool()
    index = {t: ru.ensure_track(timeline, "audio", t, "stereo") for t in track_names(sound)}

    placed, failed = 0, 0
    for i in sorted(sound["items"], key=lambda x: x["at"]):
        mpi = be.import_file(media_pool, project, i["file"], SFX_BIN)
        if not mpi:
            log(f"  ! {Path(i['file']).name}: nicht importierbar")
            failed += 1
            continue
        src_fps = float(mpi.GetClipProperty("FPS") or fps)
        rec = round(i["at"] * fps)
        length_f = round((i["at"] + i["dur"]) * fps) - rec
        src_in = round(i["in"] * src_fps)
        item = None
        for extra in (0, 1, -1, 2):
            items = media_pool.AppendToTimeline([{
                "mediaPoolItem": mpi, "startFrame": src_in,
                "endFrame": src_in + be.ceil_frames(length_f * src_fps / fps) + extra,
                "trackIndex": index[i["track"]], "recordFrame": start + rec, "mediaType": 2}])
            if items and items[0].GetDuration() == length_f:
                item = items[0]
                break
            if items:
                timeline.DeleteClips(items, False)
        if not item:
            log(f"  ! {Path(i['file']).name} bei {i['at']:.2f}s liess sich nicht framegenau einfuegen")
            failed += 1
            continue
        item.SetProperty("AudioVolume", float(sound["level_db"]))
        if abs(item.GetStart() - start - rec) > 1:
            log(f"  ! {Path(i['file']).name}: liegt bei {(item.GetStart() - start) / fps:.2f}s statt {i['at']:.2f}s")
        placed += 1
    pm.SaveProject()
    log(f"  {placed} Clips auf {', '.join(index)}, Pegel {sound['level_db']} dB, {failed} Fehler")
    log(f"Fertig: {name}")
    log.write(root)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
