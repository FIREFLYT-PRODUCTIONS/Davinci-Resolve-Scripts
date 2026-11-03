"""
FIREFLYT Edit – Selects auf die Spur SELECTS legen
==================================================
Liest SELECTS\\selects.json und legt jeden Select framegenau über seine Stelle
auf V1 der Source-Timeline, auf eine Spur namens SELECTS. Die Source-Timelines
bekommen nur diese Spur dazu. Takes, die auf SELECTS schon Clips haben, werden
übersprungen. Neue Clips bekommen BASE NODE TREE und die Color Group.

USAGE:
  python place_selects.py "<Projektordner>" [--editor FELIX] [--timelines "SONY A7IV" ...]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import resolve_util as ru  # noqa: E402

TRACK = "SELECTS"


def plan_placements(selects, v1, tl_fps, existing):
    """Rein, testbar. v1: [{file, start, end, src_start, fps}], existing: [(start, end)] auf SELECTS.
    Gibt (plan, skipped) zurück; Bereiche werden auf den V1-Clip begrenzt."""
    plan, skipped = [], []
    by_file = {item["file"].lower(): item for item in v1}
    for s in selects:
        item = by_file.get(Path(s["file"]).name.lower()) or by_file.get(s["file"].lower())
        if not item:
            skipped.append({**s, "why": "nicht in dieser Timeline"})
            continue
        if any(a < item["end"] and b > item["start"] for a, b in existing):
            skipped.append({**s, "why": "Take hat schon Selects"})
            continue
        src_end = item["src_start"] + round((item["end"] - item["start"]) * item["fps"] / float(tl_fps))
        start, end = max(s["start"], item["src_start"]), min(s["end"], src_end)
        if end - start < 2:
            skipped.append({**s, "why": "liegt ausserhalb des Clips"})
            continue
        record = common.src_to_record(item["start"], item["src_start"], start, tl_fps, item["fps"])
        plan.append({**s, "file": s["file"], "start": start, "end": end, "record": record,
                     "item_file": item["file"]})
    return plan, skipped


def v1_items(timeline):
    items = []
    for it in timeline.GetItemListInTrack("video", 1) or []:
        mpi = it.GetMediaPoolItem()
        if not mpi:
            continue
        items.append({"file": Path(mpi.GetClipProperty("File Path") or "").name, "start": it.GetStart(),
                      "end": it.GetEnd(), "src_start": it.GetSourceStartFrame(),
                      "fps": float(mpi.GetClipProperty("FPS") or 0) or 1.0, "mpi": mpi})
    return items


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="FIREFLYT Selects auf Spur SELECTS")
    parser.add_argument("folder")
    parser.add_argument("--editor", default="CONRAD")
    parser.add_argument("--timelines", nargs="*")
    args = parser.parse_args()

    log = common.Log("PLACE_SELECTS")
    root = common.claude_dir(args.folder, args.editor)
    selects = common.load_json(root / "SELECTS" / "selects.json")["selects"]
    try:
        resolve, pm, project = ru.open_project(args.folder, args.editor)
    except ru.EditError as error:
        log(f"ABBRUCH: {error}")
        log.write(root)
        return 2
    media_pool = project.GetMediaPool()
    groups = ru.group_map(project)
    sources = ru.source_timelines(project)
    if args.timelines:
        sources = {k: v for k, v in sources.items() if k in args.timelines}

    placed_files, wanted, total_new = set(), {}, 0
    for name, timeline in sources.items():
        items = v1_items(timeline)
        files = {i["file"].lower() for i in items}
        mine = [s for s in selects if Path(s["file"]).name.lower() in files]
        if not mine:
            continue
        tl_fps = float(timeline.GetSetting("timelineFrameRate"))
        index = ru.track_index(timeline, "video", TRACK)
        existing = [(it.GetStart(), it.GetEnd()) for it in timeline.GetItemListInTrack("video", index) or []] \
            if index else []
        plan, skipped = plan_placements(mine, items, tl_fps, existing)
        for s in skipped:
            if s["why"] != "nicht in dieser Timeline":
                log(f"  ~ {name}: {Path(s['file']).name} {s['start']}-{s['end']} uebersprungen ({s['why']})")
        if not plan:
            placed_files |= {Path(s["file"]).name.lower() for s in mine}
            continue
        project.SetCurrentTimeline(timeline)
        index = ru.ensure_track(timeline, "video", TRACK)
        by_file = {i["file"].lower(): i for i in items}
        new_items = []
        for p in plan:
            mpi = by_file[p["item_file"].lower()]["mpi"]
            result = media_pool.AppendToTimeline([{"mediaPoolItem": mpi, "startFrame": p["start"],
                                                   "endFrame": p["end"], "trackIndex": index,
                                                   "recordFrame": p["record"], "mediaType": 1}])
            if result:
                new_items += result
                if abs(result[0].GetStart() - p["record"]) > 1:
                    log(f"  ! {name}: {Path(p['file']).name} liegt bei {result[0].GetStart()} statt {p['record']}")
            else:
                log(f"  ! {name}: {Path(p['file']).name} {p['start']}-{p['end']} liess sich nicht einfuegen")
        ok = ru.apply_look(resolve, project, timeline, new_items, groups)
        pm.SaveProject()
        wanted[name] = [index]
        total_new += len(new_items)
        placed_files |= {Path(s["file"]).name.lower() for s in mine}
        log(f"  + {name}: {len(new_items)} Selects, {ok} mit Node Tree")

    missing = [s for s in selects if Path(s["file"]).name.lower() not in placed_files]
    if missing:
        log(f"! {len(missing)} Selects ohne passende Source-Timeline: "
            f"{', '.join(sorted({Path(s['file']).name for s in missing}))}")
    if wanted:
        project, items, ok = ru.reload_count(pm, project, wanted)
        log(f"Nach Neuladen: {ok} von {items} Clips auf {TRACK} mit Node Tree")
    log(f"Fertig: {total_new} neue Selects")
    log.write(root)
    return 0 if not missing else 1


if __name__ == "__main__":
    sys.exit(main())
