"""
FIREFLYT Edit – Resolve-Hilfen
==============================
Projekt öffnen, Timelines und Spuren finden, Look (BASE NODE TREE + Color Group)
auf neue Clips setzen und nach Neuladen kontrollieren. Verbindung und Pfade
kommen aus PROJEKT_SETUP.py, damit sie nur an einer Stelle gepflegt werden.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import PROJEKT_SETUP as ps  # noqa: E402

NODE_TREE_DRX = ps.NODE_TREE_DRX
NODE_TREE_COUNT = ps.NODE_TREE_COUNT
SOURCE_BIN_NAME = ps.SOURCE_BIN_NAME


class EditError(Exception):
    pass


def library_name(project_dir, editor="CONRAD"):
    customer = Path(project_dir).parent.name
    return customer if editor.upper() == "CONRAD" else f"{customer} - {editor.upper()}"


def open_project(project_dir, editor="CONRAD"):
    """Öffnet das Projekt des Ordners. Ist ein anderes Projekt offen, wird abgebrochen,
    damit keine ungespeicherte Arbeit verloren geht."""
    project_dir = Path(project_dir)
    name = project_dir.name
    resolve = ps.connect()
    pm = resolve.GetProjectManager()
    library = library_name(project_dir, editor)
    current = pm.GetCurrentProject()
    if current and current.GetName() == name and pm.GetCurrentDatabase().get("DbName") == library:
        return resolve, pm, current
    if current and current.GetName() != ps.UNTITLED:
        raise EditError(f"In Resolve ist '{current.GetName()}' offen. Bitte speichern und schliessen.")
    if pm.GetCurrentDatabase().get("DbName") != library:
        try:
            ps.switch_library(pm, library)
        except ps.SetupError as error:
            raise EditError(str(error))
    folders = ps.find_project_folder(pm, name)
    if folders is None:
        raise EditError(f"Projekt '{name}' nicht in Library '{library}'. Erst Setup ausfuehren.")
    try:
        project = ps.open_existing_project(pm, name, folders)
    except ps.SetupError as error:
        raise EditError(str(error))
    return resolve, pm, project


def timelines(project):
    return {project.GetTimelineByIndex(i).GetName(): project.GetTimelineByIndex(i)
            for i in range(1, project.GetTimelineCount() + 1)}


def track_index(timeline, kind, name):
    for i in range(1, timeline.GetTrackCount(kind) + 1):
        if timeline.GetTrackName(kind, i) == name:
            return i
    return None


def ensure_track(timeline, kind, name, sub_type=None):
    """Spur mit diesem Namen, sonst neue Spur oben. Gibt den Index zurück."""
    index = track_index(timeline, kind, name)
    if index:
        return index
    ok = timeline.AddTrack(kind, sub_type) if sub_type else timeline.AddTrack(kind)
    if not ok:
        raise EditError(f"Spur '{name}' liess sich nicht anlegen.")
    index = timeline.GetTrackCount(kind)
    timeline.SetTrackName(kind, index, name)
    return index


def source_timelines(project):
    """Timelines mit Clips aus dem Bin 00 - SOURCE, also die Source-Timelines des Setups."""
    result = {}
    for name, timeline in timelines(project).items():
        items = timeline.GetItemListInTrack("video", 1) or []
        if items and all(it.GetMediaPoolItem() for it in items):
            if name.startswith(project.GetName()):
                continue  # Edit-Versionen <Projekt>_vNN
            result[name] = timeline
    return result


def file_path(item):
    mpi = item.GetMediaPoolItem()
    return (mpi.GetClipProperty("File Path") or "") if mpi else ""


def group_map(project):
    """Datei -> Color Group, gelesen aus den V1-Clips der Source-Timelines."""
    groups = {}
    for timeline in source_timelines(project).values():
        for item in timeline.GetItemListInTrack("video", 1) or []:
            path = file_path(item).lower()
            if path and path not in groups:
                groups[path] = item.GetColorGroup()
    return groups


def media_pool_items(project):
    """Datei (klein geschrieben) -> MediaPoolItem, über den ganzen Media Pool."""
    found = {}

    def walk(folder):
        for clip in folder.GetClipList() or []:
            path = (clip.GetClipProperty("File Path") or "").lower()
            if path:
                found.setdefault(path, clip)
        for sub in folder.GetSubFolderList() or []:
            walk(sub)

    walk(project.GetMediaPool().GetRootFolder())
    return found


def apply_look(resolve, project, timeline, items, groups):
    """BASE NODE TREE und Color Group auf neue Clips. Gibt die Zahl mit 17 Nodes zurück."""
    project.SetCurrentTimeline(timeline)
    resolve.OpenPage("color")
    time.sleep(1)
    ok = 0
    for item in items:
        group = groups.get(file_path(item).lower())
        if group:
            item.AssignToColorGroup(group)
        item.GetNodeGraph().ApplyGradeFromDRX(str(NODE_TREE_DRX), 0)
        if item.GetNodeGraph().GetNumNodes() == NODE_TREE_COUNT:
            ok += 1
    resolve.OpenPage("edit")
    return ok


def reload_count(pm, project, wanted):
    """Speichert, lädt neu und zählt Clips mit Node Tree.
    wanted: {timeline_name: [track_index, ...]}. Gibt (project, total, ok) zurück."""
    name = project.GetName()
    pm.SaveProject()
    pm.CloseProject(project)
    project = pm.LoadProject(name)
    if not project:
        raise EditError("Projekt laesst sich nach dem Speichern nicht neu laden.")
    total = ok = 0
    by_name = timelines(project)
    for tl_name, tracks in wanted.items():
        timeline = by_name.get(tl_name)
        if not timeline:
            continue
        for track in tracks:
            for item in timeline.GetItemListInTrack("video", track) or []:
                total += 1
                ok += item.GetNodeGraph().GetNumNodes() == NODE_TREE_COUNT
    return project, total, ok
