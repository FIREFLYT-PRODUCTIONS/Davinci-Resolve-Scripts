"""
FIREFLYT Productions – Source Timeline Generator
=================================================
Scannt automatisch alle Bins unter dem SOURCE-Ordner
und legt Timelines direkt im jeweiligen Bin an.

Naming:
  Nur eine Orientierung vorhanden  →  SONY FX3
  Beide Orientierungen vorhanden   →  SONY FX3 - HORIZONTAL
                                       SONY FX3 - VERTICAL

USAGE (Resolve Console):
  exec(open(r"C:\\Pfad\\zum\\Script\\fireflyt_source_timelines.py").read())
"""

import sys
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

# Clip-Farben pro Bin  –  hier anpassen und erweitern
# Verfuegbare Farben: Orange, Apricot, Yellow, Lime, Olive, Green,
#                    Teal, Navy, Blue, Purple, Violet, Pink,
#                    Tan, Beige, Brown, Chocolate
CLIP_COLORS = {
    "SONY FX3":        "Orange",
    "SONY FX3-1":      "Orange",
    "SONY FX3-2":      "Apricot",
    "SONY A7IV":       "Yellow",
    "SONY A7IV-1":     "Yellow",
    "SONY A7IV-2":     "Yellow",
    "DJI MAVIC 3 PRO": "Tan",
    "DJI MINI 4 PRO":  "Beige",
    # Weitere Bins hier eintragen:
    # "KAMERA NAME":   "Farbe",
}

# FPS-Flags
# Jedem FPS-Bereich wird eine Flag-Farbe zugewiesen.
# Verfuegbare Farben: Orange, Apricot, Yellow, Lime, Olive, Green,
#                    Teal, Navy, Blue, Purple, Violet, Pink,
#                    Tan, Beige, Brown, Chocolate
# Format: (flag_farbe, [fps_werte])  – Werte als Float
FPS_FLAGS = [
    ("Green",  [23.976, 24.0, 25.0, 29.97, 30.0]),   # Standard-Framerates
    ("Yellow", [50.0, 59.94, 60.0]),                   # High-Speed / Slow-Mo
    ("Red",    [100.0, 120.0, 240.0]),                 # Super Slow-Mo (100fps+)
]

# Toleranz beim FPS-Vergleich (z.B. 23.976 vs 23.9760)
FPS_TOLERANCE = 0.01

# Color Group Zuweisung
# Zwei Regeltypen:
#
# 1. Einfache Regel – alle Clips in der Timeline bekommen die gleiche Group:
#    {"keyword": "SONY", "group": "S-LOG 3"}
#
# 2. Aufloesung-basierte Regel – Group haengt von der Clip-Aufloesung ab:
#    {"keyword": "MAVIC", "resolution_rules": [
#        (min_breite, max_breite, "group_name"),
#    ]}
#    Beispiel: Clips mit Breite 5000-5999px -> D-LOG, Clips mit 3840-4999px -> D-LOG M

COLOR_GROUP_RULES = [
    # Sony Kameras -> S-LOG 3
    {"keyword": "SONY", "group": "S-LOG 3"},

    # DJI Mini 4 Pro -> D-LOG M
    {"keyword": "MINI", "group": "D-LOG M"},

    # DJI Mavic 3 Pro: Wide (5.1K Hasselblad) -> D-LOG, Zoom (4K Tele) -> D-LOG M
    # Hasselblad Wide:    5120x2700 (5.1K) -> D-LOG
    # Medium Tele 70mm:   max 4096px       -> D-LOG M
    # Tele 166mm:         max 4096px       -> D-LOG M
    {"keyword": "MAVIC", "resolution_rules": [
        (5000, 9999, "D-LOG"),    # >= 5000px = Hasselblad Wide (5120x2700)
        (1000, 4999, "D-LOG M"),  # <= 4999px = Zoom-Linsen (3840 / 4096px)
    ]},
]

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
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


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


def get_clip_orientation(clip):
    props = clip.GetClipProperty()
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



def get_clip_fps(clip):
    """Liest die FPS eines Clips aus den Metadaten."""
    props = clip.GetClipProperty()
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
    for color, fps_list in FPS_FLAGS:
        for target in fps_list:
            if abs(fps - target) <= FPS_TOLERANCE:
                return color
    # Catch-all fuer 100fps+ falls nicht explizit in der Liste
    last_color, _ = FPS_FLAGS[-1]
    _, last_fps_list = FPS_FLAGS[-1]
    if fps >= 100.0:
        return last_color
    return None


def get_clip_sort_key(clip):
    props = clip.GetClipProperty()
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
    verschachtelt (SOURCE/DATE/VIDEOS/CAMERA) gleichermassen."""
    if ancestry is None:
        ancestry = []

    results = []
    clips = folder.GetClipList() or []
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


def assign_display_names(camera_bin_entries, source_bin_name):
    """Setzt entry['display_name'] fuer jeden Eintrag. Eindeutige
    Kamera-Namen bleiben unveraendert; bei Kollisionen (z.B. 'SONY FX3'
    an mehreren Aufnahmetagen) wird der naechste nicht-strukturelle
    Vorfahre (i.d.R. der Datumsordner) vorangestellt."""
    counts = Counter(e["name"] for e in camera_bin_entries)
    exclude = STRUCTURAL_ANCESTOR_NAMES | {source_bin_name.strip().upper()}
    fallback = Counter()

    for e in camera_bin_entries:
        if counts[e["name"]] == 1:
            e["display_name"] = e["name"]
            continue

        tag_segments = [s for s in e["ancestry"] if s.strip().upper() not in exclude]
        if tag_segments:
            e["display_name"] = f"{tag_segments[-1]} {e['name']}"
        else:
            fallback[e["name"]] += 1
            e["display_name"] = f"{e['name']} ({fallback[e['name']]})"


def get_all_timelines(project):
    names = set()
    count = project.GetTimelineCount()
    for i in range(1, count + 1):
        tl = project.GetTimelineByIndex(i)
        if tl:
            names.add(tl.GetName())
    return names


def create_source_timeline(media_pool, project, name, clips, width, height, fps, target_bin):
    existing = get_all_timelines(project)
    if name in existing:
        log(f"  ~ '{name}' existiert bereits – uebersprungen.")
        return None

    sorted_clips = sorted(clips, key=get_clip_sort_key)

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

    result = media_pool.AppendToTimeline(sorted_clips)
    if result:
        log(f"    → {len(sorted_clips)} Clips eingefuegt (nach Aufnahmezeit sortiert)")
    else:
        log(f"    ! Clips konnten nicht eingefuegt werden")

    return timeline



def apply_clip_colors(camera_bin_entries):
    """Setzt Clip-Farben und FPS-Flags fuer alle entdeckten Kamera-Bins."""
    log("[1/3] Clip-Farben und FPS-Flags setzen ...")
    total_colored = 0
    total_flagged = 0

    for entry in camera_bin_entries:
        bin_name = entry["name"]
        color    = CLIP_COLORS.get(bin_name)
        clips    = entry["clips"]

        for clip in clips:
            # Clip Color setzen
            if color:
                clip.SetClipColor(color)
                total_colored += 1

            # FPS-Flag setzen
            fps = get_clip_fps(clip)
            flag_color = get_flag_color_for_fps(fps)
            if flag_color:
                clip.AddFlag(flag_color)
                total_flagged += 1

        fps_info = ""
        if color:
            fps_info = f" | Farbe: {color}"
        log(f"  + '{bin_name}' ({len(clips)} Clips{fps_info})")

    log(f"  {total_colored} Clip(s) eingefaerbt, {total_flagged} FPS-Flag(s) gesetzt.\n")




def get_item_width(item):
    """Liest die Clip-Breite eines TimelineItems aus."""
    try:
        mp_item = item.GetMediaPoolItem()
        if not mp_item:
            return None
        props = mp_item.GetClipProperty()
        if not props:
            return None
        resolution = props.get("Resolution", "")
        if "x" in resolution:
            w = int(resolution.lower().split("x")[0].strip())
            return w
    except Exception:
        pass
    return None


def get_group_for_item(item, rule, group_map):
    """Gibt das ColorGroup-Objekt fuer ein TimelineItem basierend auf der Regel zurueck."""
    # Einfache Regel: alle Clips bekommen die gleiche Group
    if "group" in rule:
        grp = group_map.get(rule["group"])
        if not grp:
            log(f"  ! Color Group '{rule['group']}' nicht gefunden.")
        return grp

    # Aufloesung-basierte Regel
    if "resolution_rules" in rule:
        width = get_item_width(item)
        if width is None:
            return None
        for min_w, max_w, group_name in rule["resolution_rules"]:
            if min_w <= width <= max_w:
                grp = group_map.get(group_name)
                if not grp:
                    log(f"  ! Color Group '{group_name}' nicht gefunden.")
                return grp

    return None


def assign_color_groups(project):
    """Weist Timeline-Items Color Groups zu basierend auf COLOR_GROUP_RULES."""
    log("[3/3] Color Groups zuweisen ...")

    try:
        available_groups = project.GetColorGroupsList() or []
    except Exception:
        available_groups = []

    if not available_groups:
        log("  ! Keine Color Groups im Projekt gefunden.")
        return

    group_map = {}
    for g in available_groups:
        try:
            group_map[g.GetName()] = g
        except Exception:
            pass

    log(f"  Verfuegbare Groups: {list(group_map.keys())}")

    total_assigned = 0

    timeline_count = project.GetTimelineCount()
    for i in range(1, timeline_count + 1):
        timeline = project.GetTimelineByIndex(i)
        if not timeline:
            continue
        tl_name = timeline.GetName()

        # Passende Regel fuer diese Timeline suchen
        matched_rule = None
        for rule in COLOR_GROUP_RULES:
            if rule["keyword"].upper() in tl_name.upper():
                matched_rule = rule
                break

        if not matched_rule:
            continue

        log(f"  Timeline: '{tl_name}'")

        # Alle Video-Tracks durchgehen
        track_count = timeline.GetTrackCount("video")
        for track_idx in range(1, track_count + 1):
            items = timeline.GetItemListInTrack("video", track_idx)
            if not items:
                continue
            for item in items:
                try:
                    grp = get_group_for_item(item, matched_rule, group_map)
                    if grp:
                        result = item.AssignToColorGroup(grp)
                        if result:
                            total_assigned += 1
                except Exception as e:
                    log(f"    ! Fehler: {e}")

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
        return

    project    = resolve.GetProjectManager().GetCurrentProject()
    media_pool = project.GetMediaPool()
    root_bin   = media_pool.GetRootFolder()

    log(f"Projekt: {project.GetName()}\n")

    source_bin = find_bin_by_name(root_bin, SOURCE_BIN_NAME)
    if not source_bin:
        log(f"FEHLER: Source-Ordner '{SOURCE_BIN_NAME}' nicht gefunden.")
        return

    camera_bin_entries = find_camera_bins(source_bin)
    if not camera_bin_entries:
        log(f"Keine Kamera-Bins mit Clips unter '{SOURCE_BIN_NAME}' gefunden.")
        return

    log(f"Source-Ordner gefunden: '{SOURCE_BIN_NAME}'")
    log(f"{len(camera_bin_entries)} Kamera-Bin(s) mit Clips gefunden (rekursiv)\n")

    # Schritt 1: Clip-Farben setzen
    apply_clip_colors(camera_bin_entries)

    # Namen fuer gleichnamige Kamera-Bins an verschiedenen Tagen disambiguieren
    assign_display_names(camera_bin_entries, source_bin.GetName())

    # Schritt 2: Timelines erstellen
    log("[2/3] Source-Timelines erstellen ...\n")
    total_created = 0

    for entry in camera_bin_entries:
        cam_bin  = entry["bin"]
        clips    = entry["clips"]
        bin_name = entry["display_name"]

        log(f"Kamera-Bin: '{bin_name}'  ({len(clips)} Clips)")

        landscape_clips = [c for c in clips if get_clip_orientation(c) == "landscape"]
        portrait_clips  = [c for c in clips if get_clip_orientation(c) == "portrait"]

        both = bool(landscape_clips) and bool(portrait_clips)

        log(f"  Horizontal: {len(landscape_clips)} Clips")
        log(f"  Vertical:   {len(portrait_clips)} Clips")

        if landscape_clips:
            tl_name = f"{bin_name} - HORIZONTAL" if both else bin_name
            tl = create_source_timeline(
                media_pool, project, tl_name, landscape_clips,
                LANDSCAPE_WIDTH, LANDSCAPE_HEIGHT, FPS, cam_bin
            )
            if tl:
                total_created += 1

        if portrait_clips:
            tl_name = f"{bin_name} - VERTICAL" if both else bin_name
            tl = create_source_timeline(
                media_pool, project, tl_name, portrait_clips,
                PORTRAIT_WIDTH, PORTRAIT_HEIGHT, FPS, cam_bin
            )
            if tl:
                total_created += 1

        print()

    # Projekt-Format zuruecksetzen auf 4K 23.976
    project.SetSetting("timelineResolutionWidth",  "3840")
    project.SetSetting("timelineResolutionHeight", "2160")
    project.SetSetting("timelineFrameRate",        FPS)

    # Schritt 3: Color Groups zuweisen
    assign_color_groups(project)

    log("=" * 50)
    log(f"Fertig – {total_created} Timeline(s) erstellt.")
    log("=" * 50)


run()