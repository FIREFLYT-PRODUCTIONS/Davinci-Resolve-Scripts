"""
FIREFLYT Productions – Source Timeline Generator
=================================================
Scannt automatisch alle Bins unter dem SOURCE-Ordner, setzt Clipfarben und
FPS-Flags, legt Timelines im jeweiligen Bin an und weist Color Groups zu.

Kamera und Bildprofil kommen pro Clip aus den Metadaten der Datei, nicht aus
dem Ordnernamen. So landet z.B. ein S-Cinetone-Clip nicht in der S-LOG-3-Gruppe.

Naming:
  Nur eine Orientierung vorhanden  →  SONY FX3
  Beide Orientierungen vorhanden   →  SONY FX3 - HORIZONTAL
                                       SONY FX3 - VERTICAL

USAGE (Resolve Console):
  exec(open(r"C:\\Pfad\\zum\\Script\\BASE_PROJECT_SETUP.py").read())
"""

import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from collections import Counter


# ─────────────────────────────────────────────
#  KONFIGURATION  –  hier anpassen
# ─────────────────────────────────────────────

SOURCE_BIN_NAME  = "00 - SOURCE"

LANDSCAPE_WIDTH  = 3840
LANDSCAPE_HEIGHT = 2160
PORTRAIT_WIDTH   = 2160
PORTRAIT_HEIGHT  = 3840
FPS              = "23.976"

PORTRAIT_THRESHOLD = 1.0

# AppendToTimeline() schlaegt gelegentlich transient fehl (Race Condition:
# die frisch erstellte Timeline ist im Resolve-internen State noch nicht
# vollstaendig als "aktuelle Timeline" gesetzt). Bei Fehlschlag wird kurz
# gewartet und erneut versucht, bevor endgueltig aufgegeben wird.
APPEND_MAX_ATTEMPTS = 3
APPEND_RETRY_DELAY_SEC = 1.0

# Clip-Farben pro Kamera. Der Bin-Name hat Vorrang (z.B. SONY FX3-2 als
# zweiter Body), sonst zaehlt die Kamera aus den Metadaten.
# Verfuegbare Farben: Orange, Apricot, Yellow, Lime, Olive, Green,
#                    Teal, Navy, Blue, Purple, Violet, Pink,
#                    Tan, Beige, Brown, Chocolate
CLIP_COLORS = {
    "SONY FX3":        "Orange",
    "SONY FX3-1":      "Orange",
    "SONY FX3-2":      "Apricot",
    "SONY A7IV":       "Yellow",
    "SONY A7IV-1":     "Yellow",
    "SONY A7IV-2":     "Lime",
    "SONY A7V":        "Green",
    "DJI MAVIC 3 PRO": "Tan",
    "DJI MAVIC 4 PRO": "Brown",
    "DJI MINI 4 PRO":  "Beige",
    "DJI MINI 5 PRO":  "Chocolate",
    "DJI AVATA 2":     "Olive",
    "GOPRO HERO 11":   "Navy",
    "GOPRO HERO 13":   "Teal",
    # Weitere Kameras hier eintragen:
    # "KAMERA NAME":   "Farbe",
}

# Kamera-Erkennung aus den Metadaten: (Suchtext in der Datei, Kameraname)
MODEL_NAMES = [
    ("ILME-FX3",      "SONY FX3"),
    ("ILCE-7M4",      "SONY A7IV"),
    ("ILCE-7M5",      "SONY A7V"),
    ("DJI Mavic3",    "DJI MAVIC 3 PRO"),
    ("DJI Mavic4",    "DJI MAVIC 4 PRO"),
    ("DJI Mini4",     "DJI MINI 4 PRO"),
    ("DJI Mini5",     "DJI MINI 5 PRO"),
    ("DJI Avata2",    "DJI AVATA 2"),
    ("HERO11",        "GOPRO HERO 11"),
    ("HERO13",        "GOPRO HERO 13"),
]

# FPS-Flags als Bereiche, damit auch 47.952 oder 50 eine Flagge bekommen
# Format: (flag_farbe, von_fps, bis_fps)
FPS_FLAGS = [
    ("Green",  0.0,  31.0),    # Standard-Framerates
    ("Yellow", 31.0, 99.0),    # Slow-Mo (48, 50, 60)
    ("Red",    99.0, 9999.0),  # Super Slow-Mo (100fps+)
]

# Color Groups, die im Base-Projekt noch fehlen duerfen: Name -> Post-Clip-LUT
EXTRA_GROUPS = {
    "GP-LOG": "00 - MY LUTS\\CORRECTION LUTS\\GOPRO\\GPLOG.cube",
}

# DJI schreibt das Farbprofil nicht lesbar in die Datei. Deshalb wird gemessen, aber
# nur ueber alle Clips eines Bins, denn ein einzelnes Bild sagt zu wenig: Log erreicht
# das hellste Weiss praktisch nie. Tut das ein Viertel der Clips, war es kein Log.
DJI_NORMAL_YMAX = 975    # 10 Bit
DJI_NORMAL_SHARE = 0.25

# Pro Clip werden nur Anfang und Ende gelesen, das reicht auch bei 11-GB-Dateien
META_READ_BYTES = 4_000_000
META_READ_WORKERS = 8

# Ordnernamen, die beim rekursiven Scan komplett uebersprungen werden
# (Gross-/Kleinschreibung egal, exakter Ordnername - kein Substring-Match).
#   PHOTOS/AUDIO -> keine Timelines, keine Farben, keine Flags fuer Fotos/Audio.
#   PROXY        -> Unterordner mit Proxy-Medien derselben Kamera, keine eigene Kamera.
SKIP_FOLDER_NAMES = {"PHOTOS", "AUDIO", "PROXY"}

# Ordnernamen, die bei der Timeline-Namens-Disambiguierung ignoriert werden,
# weil sie strukturell sind (z.B. zwei "SONY FX3"-Bins an verschiedenen Tagen
# sollen nach dem Datumsordner unterschieden werden, nicht nach "VIDEOS").
STRUCTURAL_ANCESTOR_NAMES = {"VIDEOS", "AUDIO", "PHOTOS", "PROXY"}


# ─────────────────────────────────────────────
#  HILFSFUNKTIONEN
# ─────────────────────────────────────────────

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def get_resolve():
    if "resolve" in dir(__builtins__) or "resolve" in globals():
        return globals().get("resolve") or __builtins__.get("resolve")
    try:
        import DaVinciResolveScript as dvr
        return dvr.scriptapp("Resolve")
    except ImportError:
        pass
    module_paths = [
        r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules",  # noqa
        "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules",
        "/opt/resolve/Developer/Scripting/Modules",
    ]
    for path in module_paths:
        if path not in sys.path:
            sys.path.insert(0, path)
        try:
            import DaVinciResolveScript as dvr
            return dvr.scriptapp("Resolve")
        except ImportError:
            continue
    return None


def get_clip_props(clip, props_cache):
    """Liest clip.GetClipProperty() genau einmal pro Clip aus (teurer IPC-Call
    an Resolve) und cached das Ergebnis, damit Orientation/FPS/Sort-Key sich
    denselben Fetch teilen statt ihn jeweils einzeln zu wiederholen."""
    key = id(clip)
    if key not in props_cache:
        props_cache[key] = clip.GetClipProperty() or {}
    return props_cache[key]


def get_clip_orientation(clip, props_cache):
    props = get_clip_props(clip, props_cache)
    if not props:
        return "landscape"
    resolution = props.get("Resolution", "")
    if "x" in resolution:
        try:
            w, h = [int(x.strip()) for x in resolution.lower().split("x")]
            if h > 0:
                return "portrait" if (w / h) < PORTRAIT_THRESHOLD else "landscape"
        except Exception:
            pass
    try:
        w = int(props.get("Clip X", props.get("Video Width", 0)))
        h = int(props.get("Clip Y", props.get("Video Height", 0)))
        if w > 0 and h > 0:
            return "portrait" if (w / h) < PORTRAIT_THRESHOLD else "landscape"
    except Exception:
        pass
    return "landscape"


def get_clip_fps(clip, props_cache):
    """Liest die FPS eines Clips aus den Metadaten."""
    props = get_clip_props(clip, props_cache)
    if not props:
        return None
    for key in ["FPS", "Video Frame Rate", "Frame Rate"]:
        val = props.get(key, "")
        if val:
            try:
                return float(str(val).split()[0])
            except (ValueError, IndexError):
                pass
    return None


def get_flag_color_for_fps(fps):
    """Gibt die Flag-Farbe fuer einen FPS-Wert zurueck, oder None."""
    if fps is None:
        return None
    for color, low, high in FPS_FLAGS:
        if low <= fps < high:
            return color
    return None


def get_clip_sort_key(clip, props_cache):
    props = get_clip_props(clip, props_cache)
    if props:
        for key in ["Date Recorded", "Date Modified", "Date Created", "Start TC"]:
            val = props.get(key, "")
            if val:
                return val
    return clip.GetName()


def find_bin_by_name(folder, name):
    if folder.GetName() == name:
        return folder
    for sub in folder.GetSubFolderList():
        result = find_bin_by_name(sub, name)
        if result:
            return result
    return None


def find_camera_bins(folder, ancestry=None):
    """Rekursiv: liefert alle Bins mit >=1 Clip unter `folder`.
    Ueberspringt komplett Unterordner aus SKIP_FOLDER_NAMES
    (PHOTOS/AUDIO -> keine Timelines/Farben; PROXY -> keine eigene Kamera).
    Kein festes Tiefenlimit - funktioniert flach (SOURCE/CAMERA) und
    verschachtelt (SOURCE/DATE/VIDEOS/CAMERA) gleichermassen.
    Timelines im Bin zaehlen nicht als Clips, sonst stoeren sie beim erneuten Lauf."""
    if ancestry is None:
        ancestry = []

    results = []
    clips = [c for c in (folder.GetClipList() or [])
             if "Video" in str(c.GetClipProperty("Type"))]
    if clips:
        results.append({
            "bin": folder,
            "name": folder.GetName(),
            "clips": clips,
            "ancestry": list(ancestry),
        })

    for sub in (folder.GetSubFolderList() or []):
        if sub.GetName().strip().upper() in SKIP_FOLDER_NAMES:
            continue
        results.extend(find_camera_bins(sub, ancestry + [folder.GetName()]))

    return results


def camera_from_path(entry):
    """Sucht den Kameranamen im Bin oder dessen Eltern (SONY FX3/2026-05-01)."""
    for name in [entry["name"]] + list(reversed(entry["ancestry"])):
        if name.strip().upper() in CLIP_COLORS:
            return name.strip().upper()
    return None


def assign_display_names(camera_bin_entries, source_bin_name):
    """Setzt entry['display_name'] fuer jeden Eintrag. Eindeutige
    Kamera-Namen bleiben unveraendert; bei Kollisionen (z.B. 'SONY FX3'
    an mehreren Aufnahmetagen) wird der naechste nicht-strukturelle
    Vorfahre (i.d.R. der Datumsordner) vorangestellt. Liegt die Kamera ueber
    dem Bin (SONY FX3/2026-05-01), wird sie immer vorangestellt."""
    counts = Counter(e["name"] for e in camera_bin_entries)
    exclude = STRUCTURAL_ANCESTOR_NAMES | {source_bin_name.strip().upper()}
    fallback = Counter()

    for e in camera_bin_entries:
        camera = camera_from_path(e)
        if camera and camera != e["name"].strip().upper():
            e["display_name"] = f"{camera} {e['name']}"
            continue
        if counts[e["name"]] == 1:
            e["display_name"] = e["name"]
            continue

        tag_segments = [s for s in e["ancestry"] if s.strip().upper() not in exclude]
        if tag_segments:
            e["display_name"] = f"{tag_segments[-1]} {e['name']}"
        else:
            fallback[e["name"]] += 1
            e["display_name"] = f"{e['name']} ({fallback[e['name']]})"


# ─────────────────────────────────────────────
#  METADATEN  –  Kamera und Bildprofil pro Clip
# ─────────────────────────────────────────────

def read_file_ends(path):
    """Liest Anfang und Ende der Datei. Dort liegen XML, GPMF und DJI-Metadaten."""
    size = os.path.getsize(path)
    with open(path, "rb") as handle:
        data = handle.read(META_READ_BYTES)
        if size > META_READ_BYTES:
            handle.seek(max(META_READ_BYTES, size - META_READ_BYTES))
            data += handle.read()
    return data


def dji_clip_reaches_white(path):
    """True, wenn das hellste Weiss erreicht wird. None, wenn nicht messbar
    (kein ffmpeg auf dem Rechner, Clip zu kurz oder defekt)."""
    if not shutil.which("ffmpeg"):
        return None
    try:
        done = subprocess.run(
            ["ffmpeg", "-v", "error", "-skip_frame", "nokey", "-noaccurate_seek", "-ss", "1",
             "-i", path, "-frames:v", "1",
             "-vf", "scale=160:-1,signalstats,metadata=print:file=-", "-f", "null", "-"],
            capture_output=True, text=True, timeout=60,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    ymax = re.search(r"YMAX=([\d.]+)", done.stdout)
    if not ymax:
        return None
    high = float(ymax.group(1))
    return high <= 255 or high > DJI_NORMAL_YMAX  # 8 Bit gibt es bei DJI nur ohne Log


def read_clip_meta(path):
    """Liefert {'camera', 'group', 'note'} aus den Metadaten der Datei."""
    meta = {"camera": None, "group": None, "note": None}
    try:
        data = read_file_ends(path)
    except OSError as error:
        meta["note"] = f"nicht lesbar ({error})"
        return meta

    for needle, camera in MODEL_NAMES:
        if needle.encode() in data:
            meta["camera"] = camera
            break

    gamma = re.search(rb'CaptureGammaEquation" value="([^"]+)"', data)
    if gamma:
        value = gamma.group(1).decode("latin-1")
        if value.lower().startswith("s-log3"):
            meta["group"] = "S-LOG 3"
        else:
            meta["note"] = f"Sony-Profil {value}, keine Log-Gruppe"
        return meta

    ptcl = data.find(b"PTCL")
    if ptcl >= 0:
        value = data[ptcl + 8:ptcl + 16].split(b"\0")[0].decode("latin-1").strip()
        if value.upper() == "LOG":
            meta["group"] = "GP-LOG"
        else:
            meta["no_group_ok"] = True  # FLAT und Standard sehen ohne LUT besser aus
        return meta

    camera = meta["camera"] or ""
    if camera.startswith("DJI"):
        meta["group"] = "D-LOG" if camera == "DJI MAVIC 3 PRO" and b"Hasselblad" in data else "D-LOG M"
    return meta


def check_dji_bins(camera_bin_entries, jobs, clip_meta, pool):
    """Nimmt DJI-Bins ohne Log aus den Gruppen, damit die LUT das Bild nicht verfaerbt."""
    paths = {clip.GetUniqueId(): path for clip, path in jobs}
    for entry in camera_bin_entries:
        ids = [c.GetUniqueId() for c in entry["clips"]]
        ids = [i for i in ids if (clip_meta[i].get("camera") or "").startswith("DJI")]
        if not ids:
            continue
        measured = [r for r in pool.map(dji_clip_reaches_white, [paths[i] for i in ids]) if r is not None]
        if not measured:
            continue
        share = sum(measured) / len(measured)
        if share >= DJI_NORMAL_SHARE:
            log(f"  '{entry['name']}': {sum(measured)} von {len(measured)} Clips mit vollem Kontrast, kein Log")
            for i in ids:
                clip_meta[i]["group"] = None
                clip_meta[i]["note"] = "Drohne wohl nicht in Log gefilmt, keine Color Group"


def read_all_clip_meta(camera_bin_entries):
    """Liest die Metadaten aller Clips parallel. Nur Dateizugriff, keine Resolve-Aufrufe."""
    jobs = []
    for entry in camera_bin_entries:
        for clip in entry["clips"]:
            jobs.append((clip, clip.GetClipProperty("File Path") or ""))
    with ThreadPoolExecutor(max_workers=META_READ_WORKERS) as pool:
        results = list(pool.map(read_clip_meta, [path for _, path in jobs]))
        clip_meta = {clip.GetUniqueId(): meta for (clip, _), meta in zip(jobs, results)}
        check_dji_bins(camera_bin_entries, jobs, clip_meta, pool)
    return clip_meta


# ─────────────────────────────────────────────
#  TIMELINES
# ─────────────────────────────────────────────

def get_all_timelines(project):
    names = set()
    count = project.GetTimelineCount()
    for i in range(1, count + 1):
        tl = project.GetTimelineByIndex(i)
        if tl:
            names.add(tl.GetName())
    return names


def create_source_timeline(media_pool, project, name, clips, width, height, fps, target_bin, props_cache):
    existing = get_all_timelines(project)
    if name in existing:
        log(f"  ~ '{name}' existiert bereits – uebersprungen.")
        return None

    sorted_clips = sorted(clips, key=lambda c: get_clip_sort_key(c, props_cache))

    media_pool.SetCurrentFolder(target_bin)

    # Aufloesung setzen und sofort verifizieren
    project.SetSetting("timelineResolutionWidth",  str(width))
    project.SetSetting("timelineResolutionHeight", str(height))
    project.SetSetting("timelineFrameRate",        fps)

    # Verify settings took effect
    actual_w = project.GetSetting("timelineResolutionWidth")
    actual_h = project.GetSetting("timelineResolutionHeight")
    if actual_w != str(width) or actual_h != str(height):
        log(f"  ! Warnung: Aufloesung nicht uebernommen ({actual_w}x{actual_h} statt {width}x{height})")
        # Nochmal setzen
        project.SetSetting("timelineResolutionWidth",  str(width))
        project.SetSetting("timelineResolutionHeight", str(height))

    timeline = media_pool.CreateEmptyTimeline(name)
    if not timeline:
        log(f"  ! Fehler beim Erstellen: '{name}'")
        return None

    # Aufloesung direkt auf der Timeline setzen (Resolve 18+)
    timeline.SetSetting("useCustomSettings", "1")
    timeline.SetSetting("timelineResolutionWidth",  str(width))
    timeline.SetSetting("timelineResolutionHeight", str(height))
    timeline.SetSetting("timelineFrameRate",        fps)

    log(f"  ✓ '{name}' erstellt ({width}x{height} @ {fps}fps)")

    result = None
    for attempt in range(1, APPEND_MAX_ATTEMPTS + 1):
        result = media_pool.AppendToTimeline(sorted_clips)
        if result:
            break
        if attempt < APPEND_MAX_ATTEMPTS:
            log(f"    ~ Einfuegen fehlgeschlagen (Versuch {attempt}/{APPEND_MAX_ATTEMPTS}), "
                f"erneuter Versuch in {APPEND_RETRY_DELAY_SEC}s ...")
            time.sleep(APPEND_RETRY_DELAY_SEC)

    if result:
        log(f"    → {len(sorted_clips)} Clips eingefuegt (nach Aufnahmezeit sortiert)")
    else:
        log(f"    ! Clips konnten nicht eingefuegt werden (nach {APPEND_MAX_ATTEMPTS} Versuchen)")

    return timeline


def apply_clip_colors(camera_bin_entries, props_cache, clip_meta):
    """Setzt Clip-Farben und FPS-Flags fuer alle entdeckten Kamera-Bins."""
    log("[1/3] Clip-Farben und FPS-Flags setzen ...")
    total_colored = 0
    total_flagged = 0

    for entry in camera_bin_entries:
        bin_name = entry["name"]
        path_camera = camera_from_path(entry)
        cameras = Counter()

        for clip in entry["clips"]:
            meta = clip_meta.get(clip.GetUniqueId(), {})
            camera = path_camera or meta.get("camera")
            cameras[camera] += 1

            # Clip Color setzen
            color = CLIP_COLORS.get(camera)
            if color and not clip.GetClipColor():
                clip.SetClipColor(color)
                total_colored += 1

            # FPS-Flag setzen
            fps = get_clip_fps(clip, props_cache)
            flag_color = get_flag_color_for_fps(fps)
            if flag_color:
                if flag_color not in (clip.GetFlagList() or []):
                    clip.AddFlag(flag_color)
                total_flagged += 1

        names = ", ".join(str(name) for name in cameras)
        log(f"  + '{bin_name}' ({len(entry['clips'])} Clips | {names})")

    log(f"  {total_colored} Clip(s) eingefaerbt, {total_flagged} FPS-Flag(s) gesetzt.\n")


# ─────────────────────────────────────────────
#  COLOR GROUPS
# ─────────────────────────────────────────────

def ensure_extra_groups(project):
    """Legt fehlende Color Groups samt LUT an. Gibt {Name: ColorGroup} zurueck."""
    group_map = {g.GetName(): g for g in (project.GetColorGroupsList() or [])}
    for name, lut in EXTRA_GROUPS.items():
        if name in group_map:
            continue
        group = project.AddColorGroup(name)
        if not group:
            log(f"  ! Color Group '{name}' liess sich nicht anlegen.")
            continue
        if not group.GetPostClipNodeGraph().SetLUT(1, lut):
            log(f"  ! LUT fuer '{name}' nicht gefunden: {lut}")
        group_map[name] = group
        log(f"  + Color Group '{name}' angelegt")
    return group_map


def assign_color_groups(project, source_timelines, clip_meta, result):
    """Weist die Clips der neu angelegten Source-Timelines den Color Groups aus ihren
    Metadaten zu. Alle anderen Timelines bleiben unangetastet."""
    log("[3/3] Color Groups zuweisen ...")
    group_map = ensure_extra_groups(project)
    log(f"  Verfuegbare Groups: {list(group_map.keys())}")

    total_assigned = 0
    for i in range(1, project.GetTimelineCount() + 1):
        timeline = project.GetTimelineByIndex(i)
        if not timeline or timeline.GetName() not in source_timelines:
            continue
        counts = Counter()
        for track_idx in range(1, timeline.GetTrackCount("video") + 1):
            for item in timeline.GetItemListInTrack("video", track_idx) or []:
                media_item = item.GetMediaPoolItem()
                meta = clip_meta.get(media_item.GetUniqueId(), {}) if media_item else {}
                group_name = meta.get("group")
                if meta.get("note"):
                    result["notes"].append(f"{item.GetName()}: {meta['note']}")
                group = group_map.get(group_name)
                if group and item.AssignToColorGroup(group):
                    total_assigned += 1
                    counts[group_name] += 1
                else:
                    counts["keine"] += 1
                    if not meta.get("note") and not meta.get("no_group_ok") and group_name is None:
                        result["no_rule"].append(item.GetName())
        log(f"  Timeline '{timeline.GetName()}': {dict(counts)}")

    log(f"  {total_assigned} Clip(s) Color Groups zugewiesen.\n")


# ─────────────────────────────────────────────
#  HAUPTFUNKTION
# ─────────────────────────────────────────────

def run():
    log("=" * 50)
    log("FIREFLYT – Source Timeline Generator")
    log("=" * 50)

    resolve = get_resolve()
    if not resolve:
        log("FEHLER: Resolve nicht erreichbar.")
        return None

    project    = resolve.GetProjectManager().GetCurrentProject()
    media_pool = project.GetMediaPool()
    root_bin   = media_pool.GetRootFolder()

    log(f"Projekt: {project.GetName()}\n")

    source_bin = find_bin_by_name(root_bin, SOURCE_BIN_NAME)
    if not source_bin:
        log(f"FEHLER: Source-Ordner '{SOURCE_BIN_NAME}' nicht gefunden.")
        return None

    camera_bin_entries = find_camera_bins(source_bin)
    if not camera_bin_entries:
        log(f"Keine Kamera-Bins mit Clips unter '{SOURCE_BIN_NAME}' gefunden.")
        return None

    log(f"Source-Ordner gefunden: '{SOURCE_BIN_NAME}'")
    log(f"{len(camera_bin_entries)} Kamera-Bin(s) mit Clips gefunden (rekursiv)\n")

    # Cache fuer clip.GetClipProperty() - pro Clip nur einmal abgerufen statt
    # separat fuer Farben/FPS-Flags, Orientation und Sortierung.
    props_cache = {}
    result = {"timelines": [], "notes": [], "no_rule": []}

    log("Metadaten lesen ...")
    started = time.time()
    clip_meta = read_all_clip_meta(camera_bin_entries)
    log(f"  {len(clip_meta)} Clips in {time.time() - started:.0f}s\n")

    # Schritt 1: Clip-Farben setzen
    apply_clip_colors(camera_bin_entries, props_cache, clip_meta)

    # Namen fuer gleichnamige Kamera-Bins an verschiedenen Tagen disambiguieren
    assign_display_names(camera_bin_entries, source_bin.GetName())

    # Schritt 2: Timelines erstellen
    log("[2/3] Source-Timelines erstellen ...\n")
    total_created = 0
    source_timelines = set()

    for entry in camera_bin_entries:
        cam_bin  = entry["bin"]
        clips    = entry["clips"]
        bin_name = entry["display_name"]

        log(f"Kamera-Bin: '{bin_name}'  ({len(clips)} Clips)")

        landscape_clips = [c for c in clips if get_clip_orientation(c, props_cache) == "landscape"]
        portrait_clips  = [c for c in clips if get_clip_orientation(c, props_cache) == "portrait"]

        both = bool(landscape_clips) and bool(portrait_clips)

        log(f"  Horizontal: {len(landscape_clips)} Clips")
        log(f"  Vertical:   {len(portrait_clips)} Clips")

        if landscape_clips:
            tl_name = f"{bin_name} - HORIZONTAL" if both else bin_name
            tl = create_source_timeline(
                media_pool, project, tl_name, landscape_clips,
                LANDSCAPE_WIDTH, LANDSCAPE_HEIGHT, FPS, cam_bin, props_cache
            )
            if tl:
                source_timelines.add(tl_name)
                total_created += 1

        if portrait_clips:
            tl_name = f"{bin_name} - VERTICAL" if both else bin_name
            tl = create_source_timeline(
                media_pool, project, tl_name, portrait_clips,
                PORTRAIT_WIDTH, PORTRAIT_HEIGHT, FPS, cam_bin, props_cache
            )
            if tl:
                source_timelines.add(tl_name)
                total_created += 1

        print()

    # Projekt-Format zuruecksetzen auf 4K 23.976
    project.SetSetting("timelineResolutionWidth",  "3840")
    project.SetSetting("timelineResolutionHeight", "2160")
    project.SetSetting("timelineFrameRate",        FPS)

    # Schritt 3: Color Groups zuweisen
    assign_color_groups(project, source_timelines, clip_meta, result)

    result["timelines"] = sorted(source_timelines)
    log("=" * 50)
    log(f"Fertig – {total_created} Timeline(s) erstellt.")
    log("=" * 50)
    return result


SETUP_RESULT = run()
