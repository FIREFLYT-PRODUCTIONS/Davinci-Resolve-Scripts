"""
FIREFLYT Productions – Projekt-Setup
====================================
Vom fertig befuellten Projektordner zum fertigen Resolve-Projekt:

  1. Kunden-Library pruefen, bei Neukunden aus dem Template anlegen und registrieren
  2. Base-Projekt anlegen (Name = Projektordner)
  3. 01 - SOURCE unter dem Bin 00 - SOURCE importieren
  4. BASE_PROJECT_SETUP.py ausfuehren
  5. BASE NODE TREE auf alle Clips der neuen Source-Timelines legen
  6. Blackmagic Proxy Generator starten. Er rechnet im Hintergrund weiter, mit
     den Originaldateien kann sofort gearbeitet werden.

Erwartet: Z:\\2026\\NN - KUNDE\\2026-MM-DD_KUNDE_PROJEKT\\01 - SOURCE\\...

USAGE:
  Projektordner auf PROJEKT_SETUP.bat ziehen, oder:
  python PROJEKT_SETUP.py "<Projektordner>" [--editor FELIX] [--no-proxies] [--dry-run]
                          [--resume] [--close-open]

Vorhandene Projekte werden nie ueberschrieben. --resume ergaenzt nur, was fehlt,
z.B. nach einem Abbruch oder wenn Dateien nachgereicht wurden.

Exit-Codes: 0 sauber, 1 fertig mit Hinweisen, 2 Abbruch,
            3 anderes Projekt geoeffnet, 4 Projekt existiert schon
"""

import argparse
import contextlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path


# ─────────────────────────────────────────────
#  KONFIGURATION  –  hier anpassen
# ─────────────────────────────────────────────

TOOLS_DIR        = Path(r"Z:\01 - FIREFLYT FILES\TOOLS\DAVINCI RESOLVE")
TEMPLATE_DIR     = TOOLS_DIR / "BASE_PROJECT_TEMPLATE" / "Resolve Projects"
TEMPLATE_LIBRARY = "00 - BASE PROJECT TEMPLATE"
TEMPLATE_PROJECT = "2026-MM-DD_PROJECT NAME_BASE"
SETUP_SCRIPT     = TOOLS_DIR / "SCRIPS" / "BASE_PROJECT_SETUP.py"
NODE_TREE_DRX    = TOOLS_DIR / "POWERGRADES" / "BASE NODE TREES" / "BASE NODE TREE_1.1.1.drx"
NODE_TREE_COUNT  = 17

RESOLVE_DIR  = Path(r"C:\Program Files\Blackmagic Design\DaVinci Resolve")
RESOLVE_EXE  = RESOLVE_DIR / "Resolve.exe"
SCRIPT_API   = r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting"
SCRIPT_LIB   = str(RESOLVE_DIR / "fusionscript.dll")

APPDATA      = Path(os.environ.get("APPDATA", ""))
DBLIST       = APPDATA / "Blackmagic Design" / "DaVinci Resolve" / "Preferences" / "dblist.conf"
PROXY_INI    = APPDATA / "Blackmagic Design" / "Blackmagic Proxy Generator" / "Preferences" / "ProxyGeneratorSettings.ini"
# Sicherungen von dblist.conf und INI. Nicht im Temp-Ordner, den raeumt Windows auf.
BACKUP_DIR   = APPDATA / "FIREFLYT" / "projekt_setup_backups"
EXPORT_DIR   = Path(tempfile.gettempdir()) / "fireflyt_projekt_setup"

LIBRARY_PARENT  = "00 - DAVINCI RESOLVE PROJECTS"
SOURCE_DIR_NAME = "01 - SOURCE"
SOURCE_BIN_NAME = "00 - SOURCE"
UNTITLED        = "Untitled Project"

VIDEO_EXT = {".mp4", ".mov", ".mxf", ".mts", ".m2ts", ".braw", ".avi", ".mkv", ".insv"}
PHOTO_EXT = {".arw", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".dng", ".heic", ".cr3"}
AUDIO_EXT = {".wav", ".mp3", ".aac", ".m4a", ".aif", ".aiff", ".flac"}
SKIP_DIRS = {"proxy"}

# So lange darf der Proxy Generator brauchen, bis er sichtbar anfaengt
PROXY_START_SEC = 300


# ─────────────────────────────────────────────
#  HILFSFUNKTIONEN
# ─────────────────────────────────────────────

EXIT_ABORT, EXIT_PROJECT_OPEN, EXIT_PROJECT_EXISTS = 2, 3, 4


class SetupError(Exception):
    def __init__(self, message, code=EXIT_ABORT):
        super().__init__(message)
        self.code = code


LOG_LINES = []
LOG_PLAN = {}  # gesetzt, sobald der Projektordner geprueft ist, damit auch ein Abbruch ein Log bekommt


def log(msg=""):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}" if msg else ""
    print(line, flush=True)
    LOG_LINES.append(line)


class LogTee:
    """Schreibt die Ausgabe des Setup-Skripts auf den Bildschirm und ins Log."""

    def write(self, text):
        sys.__stdout__.write(text)
        sys.__stdout__.flush()
        for line in text.splitlines():
            if line.strip():
                LOG_LINES.append(line)

    def flush(self):
        sys.__stdout__.flush()


def powershell(script):
    done = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return done.stdout.strip()


def resolve_processes():
    """Liefert {pid: ist_proxy_generator}. Beide Programme heissen Resolve.exe."""
    out = powershell(
        "Get-CimInstance Win32_Process -Filter \"Name='Resolve.exe'\" | "
        "ForEach-Object { \"$($_.ProcessId)|$($_.CommandLine)\" }"
    )
    procs = {}
    for line in out.splitlines():
        pid, _, cmd = line.partition("|")
        if pid.strip().isdigit():
            procs[int(pid)] = cmd.rstrip().endswith("-pg")
    return procs


def main_resolve_running():
    return any(not is_pg for is_pg in resolve_processes().values())


def proxy_generator_running():
    return any(resolve_processes().values())


def connect(wait_sec=120):
    os.environ.setdefault("RESOLVE_SCRIPT_API", SCRIPT_API)
    os.environ.setdefault("RESOLVE_SCRIPT_LIB", SCRIPT_LIB)
    modules = os.path.join(SCRIPT_API, "Modules")
    if modules not in sys.path:
        sys.path.append(modules)
    import DaVinciResolveScript as dvr

    end = time.time() + wait_sec
    while time.time() < end:
        resolve = dvr.scriptapp("Resolve")
        if resolve and resolve.GetProjectManager():
            return resolve
        time.sleep(2)
    raise SetupError("Resolve antwortet nicht. Ist External Scripting auf Local gestellt?")


def start_resolve():
    if not main_resolve_running():
        log("  Starte Resolve ...")
        # Ganz losgeloest starten. Erbt Resolve die Ausgabe des Skripts, kann sein
        # Skript-Server haengen bleiben ("Resolve antwortet nicht").
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen([str(RESOLVE_EXE)], cwd=str(RESOLVE_DIR), creationflags=flags, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(10)
    return connect()


def quit_resolve(resolve):
    log("  Beende Resolve fuer die Library-Registrierung ...")
    resolve.Quit()
    end = time.time() + 90
    while time.time() < end:
        if not main_resolve_running():
            time.sleep(3)
            return
        time.sleep(2)
    raise SetupError("Resolve wurde nicht beendet.")


def backup(path):
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    target = BACKUP_DIR / f"{datetime.now():%Y%m%d_%H%M%S}_{path.name}"
    shutil.copy2(path, target)
    return target


# ─────────────────────────────────────────────
#  ANALYSE DES PROJEKTORDNERS
# ─────────────────────────────────────────────

def scan_source(source_dir):
    """Liefert {Ordner: [Dateien]} und zaehlt uebersprungene Dateitypen."""
    media, ignored = {}, {}
    allowed = VIDEO_EXT | PHOTO_EXT | AUDIO_EXT
    for dirpath, dirs, files in os.walk(source_dir):
        dirs[:] = sorted(d for d in dirs if d.lower() not in SKIP_DIRS and not d.startswith("."))
        found = []
        for name in sorted(files):
            if name.startswith(".") or name == "Thumbs.db":
                continue
            ext = Path(name).suffix.lower()
            if ext in allowed:
                found.append(Path(dirpath) / name)
            else:
                ignored[ext] = ignored.get(ext, 0) + 1
        if found:
            media[Path(dirpath)] = found
    return media, ignored


def analyse(folder, editor):
    project_dir = Path(str(folder).strip().strip('"'))
    if not project_dir.is_dir():
        raise SetupError(f"Ordner nicht gefunden: {project_dir}")
    # Auch aeltere Schreibweisen wie 2026-09_16_AUFINITY, 2026-01-8_DBCG oder 26-03-17_KUNDE
    if not re.match(r"^\d{2,4}-\d{1,2}[-_]\d{1,2}_", project_dir.name):
        raise SetupError(f"Ordnername passt nicht zu 2026-MM-DD_KUNDE_PROJEKT: {project_dir.name}")

    customer_dir = project_dir.parent
    library_root = customer_dir / LIBRARY_PARENT
    if not library_root.is_dir():
        raise SetupError(f"Kein Ordner '{LIBRARY_PARENT}' in {customer_dir}")

    source_dir = project_dir / SOURCE_DIR_NAME
    if not source_dir.is_dir():
        raise SetupError(f"Kein Ordner '{SOURCE_DIR_NAME}' in {project_dir}")

    media, ignored = scan_source(source_dir)
    empty = [f for files in media.values() for f in files if f.stat().st_size == 0]
    media = {folder: [f for f in files if f not in empty] for folder, files in media.items()}
    media = {folder: files for folder, files in media.items() if files}
    videos = [f for files in media.values() for f in files if f.suffix.lower() in VIDEO_EXT]
    if not videos:
        raise SetupError(f"Keine Videos in {source_dir}. Sind die Dateien schon kopiert?")

    for required in (SETUP_SCRIPT, NODE_TREE_DRX, RESOLVE_EXE, DBLIST):
        if not required.exists():
            raise SetupError(f"Nicht gefunden: {required}")

    library_name = customer_dir.name if editor == "CONRAD" else f"{customer_dir.name} - {editor}"
    return {
        "project_dir": project_dir,
        "project_name": project_dir.name,
        "customer_dir": customer_dir,
        "source_dir": source_dir,
        "editor": editor,
        "library_dir": library_root / editor,
        "library_name": library_name,
        "media": media,
        "videos": videos,
        "ignored": ignored,
        "empty": empty,
    }


# ─────────────────────────────────────────────
#  LIBRARY
# ─────────────────────────────────────────────

def dblist_path(path):
    """Resolve schreibt Pfade ohne Doppelpunkt: Z\\2026\\..."""
    return str(path).replace(":", "", 1)


def find_registered_library(library_dir):
    wanted = dblist_path(library_dir).lower().rstrip("\\")
    for line in DBLIST.read_text(encoding="utf-8").splitlines():
        parts = line.split(":")
        if len(parts) >= 2 and parts[1].lower().rstrip("\\") == wanted:
            return parts[0]
    return None


def check_library_name(plan):
    """Bricht ab, wenn der Name schon fuer einen anderen Pfad registriert ist (z.B. altes Laufwerk)."""
    if find_registered_library(plan["library_dir"]):
        return
    name = plan["library_name"]
    for line in DBLIST.read_text(encoding="utf-8").splitlines():
        parts = line.split(":")
        if parts[0] == name:
            path = parts[1] if len(parts) > 1 else "?"
            raise SetupError(f"Die Library '{name}' ist in Resolve mit einem anderen Pfad "
                             f"registriert ({path}). Bitte in Resolve pruefen.")


def register_library(name, library_dir):
    saved = backup(DBLIST)
    log(f"  Sicherung der Library-Liste: {saved}")
    # Ohne Zeilenende am Schluss wuerde der neue Eintrag an den letzten angehaengt
    ends_clean = DBLIST.read_bytes().endswith(b"\n") or DBLIST.stat().st_size == 0
    with open(DBLIST, "a", encoding="utf-8", newline="") as handle:
        handle.write(("" if ends_clean else "\r\n") + f"{name}:{dblist_path(library_dir)}::::DISK\r\n")
    if find_registered_library(library_dir) != name:
        shutil.copy2(saved, DBLIST)
        raise SetupError("Library-Eintrag liess sich nicht pruefen, Library-Liste zurueckgesetzt.")


def ensure_library(plan):
    """Gibt (Library-Name, frisch_aus_template) zurueck."""
    library_dir = plan["library_dir"]
    resolve_projects = library_dir / "Resolve Projects"
    fresh = False
    check_library_name(plan)

    if not resolve_projects.is_dir():
        log(f"  Neue Library aus dem Template: {library_dir}")
        library_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(TEMPLATE_DIR, resolve_projects,
                        ignore=shutil.ignore_patterns("Thumbs.db", ".DS_Store"))
        fresh = True

    name = find_registered_library(library_dir)
    if name:
        log(f"  Library schon registriert: {name}")
        return name, fresh

    name = plan["library_name"]
    if main_resolve_running():
        quit_resolve(connect())
    register_library(name, library_dir)
    log(f"  Library registriert: {name}")
    return name, fresh


def switch_library(pm, name):
    if not pm.SetCurrentDatabase({"DbType": "Disk", "DbName": name}):
        raise SetupError(f"Library '{name}' laesst sich nicht oeffnen.")
    if pm.GetCurrentDatabase().get("DbName") != name:
        raise SetupError(f"Library-Wechsel auf '{name}' hat nicht gegriffen.")
    pm.GotoRootFolder()


def export_template(pm):
    switch_library(pm, TEMPLATE_LIBRARY)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    drp = EXPORT_DIR / f"BASE_{datetime.now():%Y%m%d_%H%M%S}.drp"
    if not pm.ExportProject(TEMPLATE_PROJECT, str(drp), True) or not drp.exists():
        raise SetupError("Template-Projekt liess sich nicht exportieren.")
    return drp


def find_project_folder(pm, name, path=()):
    """Sucht das Projekt auch in Projektordnern der Library. Gibt den Pfad zurueck."""
    if name in (pm.GetProjectListInCurrentFolder() or []):
        return list(path)
    for folder in pm.GetFolderListInCurrentFolder() or []:
        pm.OpenFolder(folder)
        found = find_project_folder(pm, name, path + (folder,))
        pm.GotoParentFolder()
        if found is not None:
            return found
    return None


def open_existing_project(pm, name, folders):
    pm.GotoRootFolder()
    for folder in folders:
        pm.OpenFolder(folder)
    project = pm.LoadProject(name)
    if not project:
        raise SetupError(f"Projekt liess sich nicht laden: {name}")
    return project


def create_project(pm, plan, library_name, fresh, resume):
    name = plan["project_name"]
    switch_library(pm, library_name)
    existing = pm.GetProjectListInCurrentFolder() or []
    folders = find_project_folder(pm, name)
    pm.GotoRootFolder()
    if folders is not None:
        if not resume:
            raise SetupError(f"Projekt existiert schon in '{library_name}': {name}", EXIT_PROJECT_EXISTS)
        log(f"  Vorhandenes Projekt wird ergaenzt: {name}")
        return open_existing_project(pm, name, folders)

    # Frische Template-Kopie, auch nach einem Abbruch direkt nach dem Anlegen
    only_template = existing == [TEMPLATE_PROJECT] and not pm.GetFolderListInCurrentFolder()
    if (fresh or only_template) and TEMPLATE_PROJECT in existing:
        log(f"  Template-Kopie wird zum Projekt: {name}")
        project = pm.LoadProject(TEMPLATE_PROJECT)
        if not project or not project.SetName(name):
            raise SetupError("Base-Projekt liess sich nicht umbenennen.")
    else:
        drp = export_template(pm)
        switch_library(pm, library_name)
        if not pm.ImportProject(str(drp), name):
            raise SetupError("Base-Projekt liess sich nicht importieren.")
        project = pm.LoadProject(name)
        if not project:
            raise SetupError("Importiertes Projekt liess sich nicht laden.")
        drp.unlink(missing_ok=True)

    groups = [g.GetName() for g in (project.GetColorGroupsList() or [])]
    log(f"  Projekt: {project.GetName()} | Color Groups: {groups}")
    pm.SaveProject()
    return project


# ─────────────────────────────────────────────
#  IMPORT, SETUP, NODE TREE
# ─────────────────────────────────────────────

def source_bin(media_pool):
    for folder in media_pool.GetRootFolder().GetSubFolderList() or []:
        if folder.GetName() == SOURCE_BIN_NAME:
            return folder
    raise SetupError(f"Bin '{SOURCE_BIN_NAME}' fehlt im Projekt.")


def get_or_add_bin(media_pool, parent, name):
    for folder in parent.GetSubFolderList() or []:
        if folder.GetName() == name:
            return folder
    created = media_pool.AddSubFolder(parent, name)
    if not created:
        raise SetupError(f"Bin '{name}' liess sich nicht anlegen.")
    return created


def import_media(project, pm, plan, warnings):
    media_pool = project.GetMediaPool()
    root_bin = source_bin(media_pool)
    total = 0
    for folder, files in plan["media"].items():
        target = root_bin
        for part in folder.relative_to(plan["source_dir"]).parts:
            target = get_or_add_bin(media_pool, target, part)
        media_pool.SetCurrentFolder(target)
        rel = folder.relative_to(plan["source_dir"])
        known = {str(c.GetClipProperty("File Path")).lower() for c in (target.GetClipList() or [])}
        new_files = [f for f in files if str(f).lower() not in known]
        if not new_files:
            log(f"  {rel}: schon importiert")
            continue
        imported = media_pool.ImportMedia([str(f) for f in new_files]) or []
        total += len(imported)
        log(f"  {rel}: {len(imported)} von {len(new_files)}")
        # Fortlaufende Fotos fasst Resolve zu einer Sequenz zusammen, das ist kein Fehler
        is_photo = all(f.suffix.lower() in PHOTO_EXT for f in files)
        if len(imported) < len(new_files) and not (is_photo and imported):
            names = {str(c.GetClipProperty("File Path")).lower() for c in imported}
            lost = [f for f in new_files if str(f).lower() not in names]
            warnings.append(f"Nicht importiert in {rel}: {', '.join(f.name for f in lost[:6])}")
            # Was Resolve nicht lesen kann, bekommt auch keinen Proxy
            plan["videos"] = [v for v in plan["videos"] if v not in lost]
    media_pool.SetCurrentFolder(media_pool.GetRootFolder())
    pm.SaveProject()
    return total


def timeline_names(project):
    return {project.GetTimelineByIndex(i).GetName()
            for i in range(1, project.GetTimelineCount() + 1)}


def run_base_setup(resolve):
    code = SETUP_SCRIPT.read_text(encoding="utf-8")
    scope = {"resolve": resolve, "__name__": "__main__", "__builtins__": __builtins__}
    with contextlib.redirect_stdout(LogTee()):
        exec(compile(code, str(SETUP_SCRIPT), "exec"), scope)
    result = scope.get("SETUP_RESULT")
    if not result:
        raise SetupError("BASE_PROJECT_SETUP hat kein Ergebnis geliefert.")
    return result


def summarize_setup(result, warnings):
    """Macht aus den Meldungen des Setup-Skripts eine kurze Liste."""
    no_rule = sorted(set(result["no_rule"]))
    if no_rule:
        warnings.append(f"Keine Kamera-Regel, Clip ohne Color Group ({len(no_rule)}): "
                        f"{', '.join(no_rule[:6])}{' ...' if len(no_rule) > 6 else ''}")
    by_note = {}
    for line in sorted(set(result["notes"])):
        clip, _, note = line.partition(": ")
        by_note.setdefault(note, []).append(clip)
    for note, clips in by_note.items():
        warnings.append(f"{note} ({len(clips)}): {', '.join(clips[:6])}{' ...' if len(clips) > 6 else ''}")


def apply_node_tree(resolve, project, pm, new_names, warnings, resume):
    resolve.OpenPage("color")
    time.sleep(1)
    applied = 0
    for i in range(1, project.GetTimelineCount() + 1):
        timeline = project.GetTimelineByIndex(i)
        if timeline.GetName() not in new_names:
            continue
        project.SetCurrentTimeline(timeline)
        for track in range(1, timeline.GetTrackCount("video") + 1):
            for item in timeline.GetItemListInTrack("video", track) or []:
                graph = item.GetNodeGraph()
                # Beim Ergaenzen nur frische Clips, vorhandene Grades bleiben unangetastet
                if resume and graph.GetNumNodes() != 1:
                    continue
                graph.ApplyGradeFromDRX(str(NODE_TREE_DRX), 0)
                if item.GetNodeGraph().GetNumNodes() == NODE_TREE_COUNT:
                    applied += 1
                else:
                    warnings.append(f"Node Tree fehlt: {timeline.GetName()} / {item.GetName()}")
        pm.SaveProject()
    resolve.OpenPage("edit")
    return applied


def reload_and_check(pm, project, new_names):
    """Laedt das Projekt neu und zaehlt die Clips mit vollstaendigem Node Tree."""
    name = project.GetName()
    pm.SaveProject()
    pm.CloseProject(project)
    project = pm.LoadProject(name)
    if not project:
        raise SetupError("Projekt laesst sich nach dem Speichern nicht neu laden.")

    items = no_tree = 0
    for i in range(1, project.GetTimelineCount() + 1):
        timeline = project.GetTimelineByIndex(i)
        if timeline.GetName() not in new_names:
            continue
        for track in range(1, timeline.GetTrackCount("video") + 1):
            for item in timeline.GetItemListInTrack("video", track) or []:
                items += 1
                if item.GetNodeGraph().GetNumNodes() != NODE_TREE_COUNT:
                    no_tree += 1
    return project, items, no_tree


def clips_outside_timelines(project, warnings):
    """Beim Ergaenzen: neue Clips landen im Bin, aber nicht in vorhandenen Timelines."""
    used = set()
    for i in range(1, project.GetTimelineCount() + 1):
        timeline = project.GetTimelineByIndex(i)
        for track in range(1, timeline.GetTrackCount("video") + 1):
            for item in timeline.GetItemListInTrack("video", track) or []:
                media_item = item.GetMediaPoolItem()
                if media_item:
                    used.add(media_item.GetUniqueId())
    missing = []

    def walk(folder, skip):
        for clip in folder.GetClipList() or []:
            if not skip and "Video" in str(clip.GetClipProperty("Type")) and clip.GetUniqueId() not in used:
                missing.append(clip.GetName())
        for sub in folder.GetSubFolderList() or []:
            walk(sub, skip or sub.GetName().upper() in {"PHOTOS", "AUDIO"})

    walk(source_bin(project.GetMediaPool()), False)
    if missing:
        warnings.append(f"Neu im Bin, aber nicht in der vorhandenen Timeline ({len(missing)}): "
                        f"{', '.join(missing[:6])}{' ...' if len(missing) > 6 else ''}")


# ─────────────────────────────────────────────
#  PROXY GENERATOR
# ─────────────────────────────────────────────

def qt_ini_string(value):
    """Schreibt einen Wert so, wie Qt ihn in INI-Dateien erwartet (\\\\ und \\xHH)."""
    out, after_hex = [], False
    for char in value:
        code = ord(char)
        if char == "\\":
            out.append("\\\\")
            after_hex = False
        elif code > 126 or code < 32 or (after_hex and char in "0123456789abcdefABCDEF"):
            out.append(f"\\x{code:x}")
            after_hex = True
        else:
            out.append(char)
            after_hex = False
    text = "".join(out)
    return f'"{text}"' if any(c in text for c in ",;=") else text


def watch_folders(videos):
    """Oberste Ordner mit Videos: VIDEOS, sonst der Kamera-Ordner (auch bei <Tag>/VIDEOS/...)."""
    folders = set()
    for video in videos:
        parents = [p for p in video.parents if p.name.upper() == "VIDEOS"]
        folders.add(parents[-1] if parents else video.parent)
    return sorted(folders, key=str)


def set_watch_folders(folders):
    raw = PROXY_INI.read_text(encoding="latin-1") if PROXY_INI.exists() else "[General]\r\n"
    entry = "watchFolderList=" + ", ".join(qt_ini_string(str(f)) for f in folders)
    if re.search(r"(?m)^watchFolderList=", raw):
        raw = re.sub(r"(?m)^watchFolderList=.*?(?=\r?$)", lambda _: entry, raw)
    else:
        raw = raw.replace("[General]", "[General]\r\n" + entry, 1)
    PROXY_INI.parent.mkdir(parents=True, exist_ok=True)
    PROXY_INI.write_text(raw, encoding="latin-1", newline="")


def press_proxy_start(pid):
    """Der Generator rechnet erst nach Klick auf Start. Klick per UI Automation."""
    return powershell(rf"""
Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
$root=[Windows.Automation.AutomationElement]::RootElement
$cond=New-Object Windows.Automation.PropertyCondition([Windows.Automation.AutomationElement]::ProcessIdProperty,{pid})
$end=(Get-Date).AddSeconds(90)
while((Get-Date) -lt $end){{
  $win=$root.FindFirst([Windows.Automation.TreeScope]::Children,$cond)
  if($win){{
    foreach($e in $win.FindAll([Windows.Automation.TreeScope]::Descendants,[Windows.Automation.Condition]::TrueCondition)){{
      if($e.Current.Name -eq 'Start' -and $e.Current.IsEnabled){{
        $p=$null
        if($e.TryGetCurrentPattern([Windows.Automation.InvokePattern]::Pattern,[ref]$p)){{ Start-Sleep -Seconds 5; $p.Invoke(); 'OK'; exit 0 }}
      }}
    }}
  }}
  Start-Sleep -Seconds 2
}}
'NICHT GEFUNDEN'
""")


def missing_proxies(videos):
    return [v for v in videos if not (v.parent / "Proxy" / (v.stem + ".mov")).exists()]


def proxy_generator_is_working(videos, open_count):
    """True, sobald eine Arbeitsdatei da ist oder ein Proxy dazukommt."""
    for folder in {v.parent / "Proxy" for v in videos}:
        if folder.is_dir() and any(e.name.endswith((".lock", ".tmp")) for e in os.scandir(folder)):
            return True
    return len(missing_proxies(videos)) < open_count


def start_proxies(plan, warnings):
    """Startet den Generator und wartet nur, bis er sichtbar rechnet."""
    videos = plan["videos"]
    open_count = len(missing_proxies(videos))
    if not open_count:
        log("  Alle Proxys sind schon da.")
        return

    folders = watch_folders(videos)
    if proxy_generator_running():
        watched = PROXY_INI.read_text(encoding="latin-1") if PROXY_INI.exists() else ""
        unwatched = [f for f in folders if qt_ini_string(str(f)) not in watched]
        if unwatched:
            listed = "; ".join(str(f) for f in unwatched)
            warnings.append(f"Proxy Generator laeuft schon, {open_count} Proxys offen. "
                            f"Dort mit Add hinzufuegen: {listed}")
        else:
            log(f"  Der laufende Generator ueberwacht diesen Ordner schon, {open_count} Proxys offen.")
        return

    if PROXY_INI.exists():
        backup(PROXY_INI)
    set_watch_folders(folders)

    process = subprocess.Popen(
        [str(RESOLVE_EXE), "-pg"], cwd=str(RESOLVE_DIR),
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    answer = press_proxy_start(process.pid)
    if answer != "OK":
        warnings.append(f"Start im Proxy Generator nicht ausgeloest ({answer}). "
                        "Er ist offen, bitte dort Start druecken.")
        return

    end = time.time() + PROXY_START_SEC
    while time.time() < end:
        if proxy_generator_is_working(videos, open_count):
            log(f"  Proxy Generator rechnet im Hintergrund: {open_count} Proxys offen.")
            log("  Du kannst schon mit den Originaldateien arbeiten.")
            return
        time.sleep(3)
    warnings.append("Proxy Generator hat nicht angefangen. Er ist offen, bitte dort pruefen.")


# ─────────────────────────────────────────────
#  HAUPTFUNKTION
# ─────────────────────────────────────────────

def write_log(plan):
    target = plan["project_dir"] / f"00 - {plan['editor']}" / "CLAUDE" / "LOGS"
    try:
        target.mkdir(parents=True, exist_ok=True)
        (target / f"PROJEKT_SETUP_{datetime.now():%Y%m%d_%H%M%S}.log").write_text(
            "\n".join(LOG_LINES), encoding="utf-8")
    except OSError as error:
        log(f"Log nicht geschrieben: {error}")


def run(args):
    warnings = []
    plan = analyse(args.folder, args.editor.upper())
    if not args.dry_run:
        LOG_PLAN.update(plan)
    photos = sum(1 for files in plan["media"].values() for f in files if f.suffix.lower() in PHOTO_EXT)
    log("=" * 50)
    log("FIREFLYT – Projekt-Setup")
    log("=" * 50)
    log(f"Projekt: {plan['project_name']}")
    log(f"Kunde:   {plan['customer_dir'].name} ({plan['editor']})")
    log(f"Medien:  {len(plan['videos'])} Videos, {photos} Fotos, {len(plan['media'])} Ordner, "
        f"{sum(f.stat().st_size for files in plan['media'].values() for f in files) / 1e9:.1f} GB")
    for folder, files in plan["media"].items():
        log(f"  {folder.relative_to(plan['source_dir'])}: {len(files)}")
    if plan["ignored"]:
        log(f"Ignoriert: {plan['ignored']}")
    if plan["empty"]:
        names = ", ".join(f.name for f in plan["empty"][:6])
        log(f"! Leere Dateien, werden uebersprungen ({len(plan['empty'])}): {names}")
        warnings.append(f"Leere Dateien uebersprungen, Kopie pruefen: {names}")

    check_library_name(plan)
    registered = find_registered_library(plan["library_dir"])
    has_library = (plan["library_dir"] / "Resolve Projects").is_dir()
    log(f"Library: {registered or plan['library_name']} "
        f"({'vorhanden' if has_library else 'wird neu angelegt'}, "
        f"{'registriert' if registered else 'wird registriert'})")
    log()
    if args.dry_run:
        log("Probelauf, nichts geaendert.")
        return 0

    if main_resolve_running():
        pm = connect().GetProjectManager()
        current = pm.GetCurrentProject()
        if current and current.GetName() != UNTITLED:
            if not args.close_open:
                raise SetupError(f"In Resolve ist '{current.GetName()}' geoeffnet. "
                                 "Bitte speichern und schliessen, dann neu starten.", EXIT_PROJECT_OPEN)
            log(f"Speichere und schliesse '{current.GetName()}' ...")
            pm.SaveProject()
            pm.CloseProject(current)

    log("[1/6] Library ...")
    library_name, fresh = ensure_library(plan)

    log("[2/6] Projekt anlegen ...")
    resolve = start_resolve()
    pm = resolve.GetProjectManager()
    project = create_project(pm, plan, library_name, fresh, args.resume)
    resolve.OpenPage("media")

    log("[3/6] Medien importieren ...")
    imported = import_media(project, pm, plan, warnings)
    log(f"  {imported} Eintraege importiert.")

    log("[4/6] BASE_PROJECT_SETUP ...")
    before = timeline_names(project)
    setup_result = run_base_setup(resolve)
    pm.SaveProject()
    summarize_setup(setup_result, warnings)
    new_names = set(setup_result["timelines"])
    if not new_names and not args.resume:
        raise SetupError("BASE_PROJECT_SETUP hat keine Timelines erzeugt.")
    if args.resume:
        log(f"  Neue Timelines: {sorted(new_names) or 'keine'}")

    log("[5/6] BASE NODE TREE ...")
    applied = apply_node_tree(resolve, project, pm, new_names, warnings, args.resume)
    project, items, no_tree = reload_and_check(pm, project, new_names)
    if args.resume:
        clips_outside_timelines(project, warnings)
    log(f"  {applied} angewendet. Nach Neuladen: {items - no_tree} von {items} Clips mit {NODE_TREE_COUNT} Nodes.")
    if no_tree and not args.resume:
        warnings.append(f"{no_tree} Clip(s) ohne vollstaendigen Node Tree.")

    if args.no_proxies:
        log("[6/6] Proxys uebersprungen.")
    else:
        log("[6/6] Proxy Generator ...")
        start_proxies(plan, warnings)
    pm.SaveProject()

    log()
    log("=" * 50)
    log(f"Fertig: {project.GetName()} in Library '{library_name}'")
    log(f"{len(new_names)} Timelines: {sorted(new_names)}")
    if warnings:
        log(f"{len(warnings)} Hinweis(e):")
        for warning in warnings:
            log(f"  ! {warning}")
    else:
        log("Keine Hinweise.")
    log("=" * 50)
    write_log(plan)
    return 1 if warnings else 0


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="FIREFLYT Projekt-Setup")
    parser.add_argument("folder", help="Projektordner, z. B. Z:\\2026\\23 - BRX\\2026-10-04_BRX_THE FIRST TABLE")
    parser.add_argument("--editor", default="CONRAD", choices=["CONRAD", "FELIX", "conrad", "felix"])
    parser.add_argument("--no-proxies", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true", help="Vorhandenes Projekt ergaenzen")
    parser.add_argument("--close-open", action="store_true", help="Offenes Projekt speichern und schliessen")
    args = parser.parse_args()
    try:
        return run(args)
    except SetupError as error:
        log(f"ABBRUCH: {error}")
        if LOG_PLAN:
            write_log(LOG_PLAN)
        return error.code


if __name__ == "__main__":
    sys.exit(main())
