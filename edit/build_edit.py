"""
FIREFLYT Edit – Base Edit als neue Timeline bauen
=================================================
Liest EDIT\\vNN.json (Schnittliste von Claude) und legt die Timeline
<Projekt>_vNN an: Shots auf V1, Alternativen auf ALT 1 / ALT 2, die Musik roh
auf Taktgrenzen geschnitten auf MUSIK, Marker für Grafikplätze. Eine vorhandene
Version wird nie verändert. Alle Clips bekommen BASE NODE TREE und Color Group.

USAGE:
  python build_edit.py "<Projektordner>" v01 [--editor FELIX] [--check]

--check prüft nur die Schnittliste, ohne Resolve.
"""

import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

TRACKS = ("V1", "ALT 1", "ALT 2")
BAR_TOLERANCE = 0.03     # Sekunden
TIMELINE_BIN = ("02 - TIMELINES",)
MUSIC_BIN = ("01 - ASSETS", "MUSIC")


# ─────────────────────────────────────────────
#  PRÜFEN UND RECHNEN (rein, testbar)
# ─────────────────────────────────────────────

def fill_zoom(clip_w, clip_h, tl_w, tl_h):
    """Zoom, mit dem ein eingepasster Clip das Bild füllt (Querformat in Hochkant und umgekehrt)."""
    fit = min(tl_w / clip_w, tl_h / clip_h)
    fill = max(tl_w / clip_w, tl_h / clip_h)
    return round(fill / fit, 4) if fill / fit > 1.001 else 1.0


def ceil_frames(x):
    """Aufrunden ohne Rauschen: 23,976024 zu 23,976 ergibt sonst aus 23 Frames 24."""
    return math.ceil(x - 1e-3)


def shot_frames(shots, takes, fps):
    """Timeline- und Quell-Frames pro Shot. Längen aus gerundeten Start- und Endframes,
    damit aufeinanderfolgende Shots ohne Lücke anschließen."""
    by_key = {t["key"]: t for t in takes}
    plan = []
    for shot in shots:
        take = by_key[shot["key"]]
        rec = round(shot["record"] * fps)
        length = round((shot["record"] + shot["dur"]) * fps) - rec
        src_in = round(shot["from"] * take["fps"])
        src_out = src_in + ceil_frames(length * take["fps"] / fps)
        plan.append({**shot, "file": take["file"], "rec": rec, "len": length,
                     "src_in": src_in, "src_out": src_out})
    return plan


def validate_edit(edit, takes, music):
    """Liefert eine Liste von Problemen, leer = in Ordnung."""
    problems = []
    fps = common.fps_value(edit["format"]["fps"])
    by_key = {t["key"]: t for t in takes}
    for shot in edit["shots"]:
        if shot["track"] not in TRACKS:
            problems.append(f"{shot['key']}: unbekannte Spur {shot['track']}")
        take = by_key.get(shot["key"])
        if not take:
            problems.append(f"{shot['key']}: unbekannter Take")
            continue
        a, b = shot["from"], shot["from"] + shot["dur"]
        if not any(s - 0.01 <= a and b <= e + 0.01 for s, e in take["clean"]):
            problems.append(f"{shot['key']} {a:.2f}-{b:.2f}s: nicht in einem sauberen Abschnitt")
    if problems:
        return problems

    plan = shot_frames(edit["shots"], takes, fps)
    v1 = sorted((p for p in plan if p["track"] == "V1"), key=lambda p: p["rec"])
    pos = 0
    for p in v1:
        if p["rec"] > pos:
            problems.append(f"Luecke auf V1 vor {p['key']} bei {p['record']:.2f}s")
        elif p["rec"] < pos:
            problems.append(f"Ueberlappung auf V1 bei {p['key']} {p['record']:.2f}s")
        pos = p["rec"] + p["len"]
    music_len = sum(round(e * fps) - round(s * fps) for s, e in edit["music"]["segments"])
    if abs(pos - music_len) > 1:
        problems.append(f"V1 ist {pos} Frames lang, die Musik {music_len}")
    for s, e in edit["music"]["segments"]:
        for t in (s, e):
            if not any(abs(t - b) <= BAR_TOLERANCE for b in music["bars"]):
                problems.append(f"Musikschnitt bei {t:.3f}s liegt nicht auf einem Takt")
    for p in plan:
        if p["track"] != "V1" and not any(v["rec"] < p["rec"] + p["len"] and p["rec"] < v["rec"] + v["len"]
                                          for v in v1):
            problems.append(f"{p['track']} {p['key']} bei {p['record']:.2f}s liegt ueber keinem V1-Shot")
    for m in edit.get("markers", []):
        if not 0 <= m["at"] * fps <= pos:
            problems.append(f"Marker {m['name']} liegt ausserhalb der Timeline")
    return problems


# ─────────────────────────────────────────────
#  RESOLVE
# ─────────────────────────────────────────────

def get_bin(media_pool, path):
    folder = media_pool.GetRootFolder()
    for name in path:
        sub = next((f for f in folder.GetSubFolderList() or [] if f.GetName() == name), None)
        folder = sub or media_pool.AddSubFolder(folder, name)
    return folder


def import_file(media_pool, project, path, bin_path):
    import resolve_util as ru
    existing = ru.media_pool_items(project).get(str(path).lower())
    if existing:
        return existing
    media_pool.SetCurrentFolder(get_bin(media_pool, bin_path))
    items = media_pool.ImportMedia([str(path)])
    return items[0] if items else None


def create_timeline(project, media_pool, name, width, height, fps):
    """Neue Timeline mit eigenem Format. Die Projekteinstellung kommt danach zurück."""
    keys = ("timelineResolutionWidth", "timelineResolutionHeight", "timelineFrameRate")
    before = {k: project.GetSetting(k) for k in keys}
    project.SetSetting("timelineResolutionWidth", str(width))
    project.SetSetting("timelineResolutionHeight", str(height))
    media_pool.SetCurrentFolder(get_bin(media_pool, TIMELINE_BIN))
    timeline = media_pool.CreateEmptyTimeline(name)
    if timeline:
        timeline.SetSetting("useCustomSettings", "1")
        timeline.SetSetting("timelineResolutionWidth", str(width))
        timeline.SetSetting("timelineResolutionHeight", str(height))
        timeline.SetSetting("timelineFrameRate", str(fps))
    for k, v in before.items():
        if k != "timelineFrameRate":
            project.SetSetting(k, v)
    return timeline


def place_music(media_pool, timeline, track, mpi, segments, tl_fps, log):
    """Musik roh aneinander, Längen in Timeline-Frames exakt, Quell-Frames in der Clip-Framerate."""
    src_fps = float(mpi.GetClipProperty("FPS") or tl_fps)
    start = timeline.GetStartFrame()
    pos = 0
    for s, e in segments:
        length = round(e * tl_fps) - round(s * tl_fps)
        src_in = round(s * src_fps)
        for extra in (0, 1, -1, 2):
            n_src = ceil_frames(length * src_fps / tl_fps) + extra
            items = media_pool.AppendToTimeline([{"mediaPoolItem": mpi, "startFrame": src_in,
                                                  "endFrame": src_in + n_src, "trackIndex": track,
                                                  "recordFrame": start + pos, "mediaType": 2}])
            if items and items[0].GetDuration() == length:
                break
            if items:
                timeline.DeleteClips(items, False)
        else:
            log(f"  ! Musik {s:.2f}-{e:.2f}s nicht framegenau, Laenge pruefen")
        pos += length
    return pos


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="FIREFLYT Base Edit bauen")
    parser.add_argument("folder")
    parser.add_argument("version")
    parser.add_argument("--editor", default="CONRAD")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    log = common.Log(f"BUILD_EDIT_{args.version}")
    root = common.claude_dir(args.folder, args.editor)
    edit = common.load_json(root / "EDIT" / f"{args.version}.json")
    takes = common.load_json(root / "SELECTS" / "takes.json")["takes"]
    music_info = common.load_json(edit["music"]["analysis"])
    problems = validate_edit(edit, takes, music_info)
    for p in problems:
        log(f"! {p}")
    if problems:
        log("ABBRUCH: Schnittliste ist nicht in Ordnung.")
        log.write(root)
        return 2
    log("Schnittliste geprueft: in Ordnung")
    if args.check:
        return 0

    import resolve_util as ru
    try:
        resolve, pm, project = ru.open_project(args.folder, args.editor)
    except ru.EditError as error:
        log(f"ABBRUCH: {error}")
        log.write(root)
        return 2
    name = f"{project.GetName()}_{args.version}"
    if name in ru.timelines(project):
        log(f"ABBRUCH: '{name}' gibt es schon. Eine vorhandene Version wird nie veraendert.")
        log.write(root)
        return 4

    fmt = edit["format"]
    fps = common.fps_value(fmt["fps"])
    media_pool = project.GetMediaPool()
    pool = ru.media_pool_items(project)
    groups = ru.group_map(project)
    timeline = create_timeline(project, media_pool, name, fmt["width"], fmt["height"], fmt["fps"])
    if not timeline:
        log("ABBRUCH: Timeline liess sich nicht anlegen.")
        log.write(root)
        return 2
    project.SetCurrentTimeline(timeline)
    timeline.SetTrackName("video", 1, "V1")
    alt_index = {"V1": 1}
    for alt in ("ALT 1", "ALT 2"):
        if any(s["track"] == alt for s in edit["shots"]):
            alt_index[alt] = ru.ensure_track(timeline, "video", alt)
    timeline.SetTrackName("audio", 1, "MUSIK")

    music = import_file(media_pool, project, edit["music"]["file"], MUSIC_BIN)
    if not music:
        log(f"ABBRUCH: Musik nicht importierbar: {edit['music']['file']}")
        log.write(root)
        return 2
    music_len = place_music(media_pool, timeline, 1, music, edit["music"]["segments"], fps, log)
    log(f"  Musik: {len(edit['music']['segments'])} Teile, {music_len / fps:.2f}s")

    start = timeline.GetStartFrame()
    new_items, zoomed = [], 0
    for p in shot_frames(edit["shots"], takes, fps):
        mpi = pool.get(p["file"].lower())
        if not mpi:
            log(f"  ! {p['key']}: nicht im Media Pool")
            continue
        items = media_pool.AppendToTimeline([{"mediaPoolItem": mpi, "startFrame": p["src_in"],
                                              "endFrame": p["src_out"], "trackIndex": alt_index[p["track"]],
                                              "recordFrame": start + p["rec"], "mediaType": 1}])
        if not items:
            log(f"  ! {p['key']} {p['track']} bei {p['record']:.2f}s liess sich nicht einfuegen")
            continue
        item = items[0]
        if item.GetStart() != start + p["rec"] or item.GetDuration() != p["len"]:
            log(f"  ! {p['key']}: liegt bei {item.GetStart() - start}/{item.GetDuration()} "
                f"statt {p['rec']}/{p['len']}")
        w, h = (mpi.GetClipProperty("Resolution") or "0x0").split("x")
        zoom = p.get("zoom") or fill_zoom(int(w), int(h), fmt["width"], fmt["height"])
        if zoom != 1.0:
            item.SetProperty("ZoomX", zoom)
            item.SetProperty("ZoomY", zoom)
            zoomed += 1
        new_items.append(item)
    for m in edit.get("markers", []):
        timeline.AddMarker(round(m["at"] * fps), m.get("color", "Blue"), m["name"], m.get("note", ""), 1)

    ok = ru.apply_look(resolve, project, timeline, new_items, groups)
    pm.SaveProject()
    log(f"  {len(new_items)} Clips ({zoomed} gezoomt), {ok} mit Node Tree, "
        f"{len(edit.get('markers', []))} Marker")
    project, total, ok = ru.reload_count(pm, project, {name: list(alt_index.values())})
    log(f"Nach Neuladen: {ok} von {total} Clips mit Node Tree")
    log(f"Fertig: {name}")
    log.write(root)
    return 0 if ok == total else 1


if __name__ == "__main__":
    sys.exit(main())
