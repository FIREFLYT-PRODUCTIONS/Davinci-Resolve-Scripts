# fireflyt-edit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die Unterfunktionen Selects, References, Base Edit und Sound Design des Skills `fireflyt-edit` bauen und am Demo-Projekt testen.

**Architecture:** Python-Skripte unter `SCRIPS\edit\` erledigen alles Messbare und alle Resolve-Schreibvorgänge. Claude trifft die Auswahl (Selects, Schnittliste, Sound-Liste) und schreibt sie als JSON nach `00 - <EDITOR>\CLAUDE\`. Die Skripte lesen diese JSON-Dateien und setzen sie in Resolve um. Reine Logik (Framemathematik, Segmentierung, Validierung) steckt in testbaren Funktionen ohne Resolve.

**Tech Stack:** Python 3.14, ffmpeg 9, numpy, opencv 5, librosa 1.0, faster_whisper (CUDA), DaVinci Resolve 21.1.2 Scripting API, `unittest`.

## Global Constraints

- Nichts überschreiben: Source-Timelines bekommen nur die Spur `SELECTS` dazu. Base Edit legt immer eine neue Version an, Sound Design arbeitet auf einer Kopie (`_SD`).
- Neue Timeline-Clips bekommen immer `BASE NODE TREE` und die Color Group des Media-Pool-Clips (aus dessen Source-Timeline).
- Unsichere Shot-Wahl als Alternativen auf `ALT 1` und `ALT 2`.
- Musik nur roh schneiden, kein Ducking. Musikschnitt nur auf Taktgrenzen.
- Keine Exporte. Kein Schlusspunkt in Grafiken.
- Nur Material des aktuellen Kunden. Kundenmaterial bleibt lokal.
- Claude-Ablage: `<Projekt>\00 - <EDITOR>\CLAUDE\` mit `BRIEFING.md`, `REFERENCES.md`, `SELECTS\`, `EDIT\`, `SOUND\`, `LOGS\`.

## Geprüfte API-Fakten (2026-11-03, Resolve 21.1.2, Demo-Projekt)

- `MediaPool.AppendToTimeline([{"mediaPoolItem", "startFrame", "endFrame", "trackIndex", "recordFrame", "mediaType": 1}])` legt framegenau auf eine Zusatzspur. `endFrame` ist exklusiv, Frames sind Quell-Frames des Clips.
- Clips mit anderer Framerate laufen in Echtzeit: Timeline-Frames = Quell-Frames × Timeline-fps / Clip-fps. Formel: `record = item.GetStart() + round((src − item.GetSourceStartFrame()) × tl_fps / clip_fps)`.
- `AssignToColorGroup` und `GetNodeGraph().ApplyGradeFromDRX(drx, 0)` (Color-Seite offen) wirken auf neue Clips und halten nach Neuladen.
- `Timeline.AddTrack("video")`, `SetTrackName`, `DuplicateTimeline`, `MediaPool.DeleteTimelines` funktionieren.

## Dateien

```
SCRIPS\edit\
  common.py           Pfade, Claude-Ablage, JSON, Framemathematik, ffprobe
  resolve_util.py     Verbindung, Projekt öffnen, Timelines, Spuren, Look setzen, Neuladen-Kontrolle
  analyse_takes.py    Technik-Durchlauf und Kontaktbilder        -> SELECTS\takes.json, SELECTS\sheets\
  transcribe.py       Transkript lokal mit faster_whisper        -> SELECTS\transcripts.json
  place_selects.py    SELECTS\selects.json auf Spur SELECTS
  measure_video.py    Länge, Schnitte, Schnitte pro Sekunde eigener Videos (References)
  analyse_music.py    Tempo, Beats, Takte, Abschnitte, Energie   -> EDIT\music_<track>.json
  build_edit.py       EDIT\vNN.json als neue Timeline <Projekt>_vNN
  place_sound.py      SOUND\vNN.json auf Kopie <Projekt>_vNN_SD
  tests\              unittest, ohne Resolve
C:\Users\conra\.claude\skills\fireflyt-edit\references\
  selects.md  references.md  base-edit.md  sound-design.md  craft-editing.md  craft-sound.md
```

## JSON-Formate (Schnittstellen zwischen Claude und Skripten)

`SELECTS\takes.json` (analyse_takes):
```json
{"takes": [{"key": "T001", "file": "<abs>", "proxy": "<abs|null>", "fps": 59.94, "frames": 2010,
  "width": 3840, "height": 2160, "duration": 33.5,
  "clean": [[1.0, 7.5], [12.0, 20.0]], "rejected": [{"from": 7.5, "to": 12.0, "why": "wackelig"}],
  "sheet": "sheet_003.jpg"}]}
```

`SELECTS\selects.json` (Claude):
```json
{"selects": [{"file": "<abs>", "start": 600, "end": 840, "rating": 4, "why": "...", "content": "Stichworte"}]}
```
`start`/`end` sind Quell-Frames, `end` exklusiv.

`EDIT\vNN.json` (Claude):
```json
{"version": "v01", "format": {"width": 2160, "height": 3840, "fps": "23.976"},
 "music": {"file": "<abs>", "segments": [[0.0, 16.0], [48.0, 64.0]]},
 "shots": [{"file": "<abs>", "src_in": 600, "src_out": 700, "record": 0.0, "track": "V1", "audio": false, "zoom": null}],
 "markers": [{"at": 28.0, "name": "LOGO", "note": "Platz fuer Logo"}]}
```
`record` in Sekunden ab Timeline-Start. `track` ist `V1`, `ALT 1` oder `ALT 2`.

`SOUND\vNN.json` (Claude):
```json
{"version": "v01", "level_db": -15,
 "items": [{"track": "SFX", "file": "<abs audio>", "at": 3.5, "in": 0.0, "dur": 1.2, "source": "artlist", "why": "..."},
           {"track": "ATMO", "file": "<abs MP4>", "at": 0.0, "in": 4.0, "dur": 12.0, "source": "kamera", "why": "..."}]}
```

---

### Task 1: common.py + resolve_util.py

**Interfaces – Produces:**
- `common.claude_dir(project_dir, editor) -> Path` (legt Unterordner an)
- `common.load_json(path)`, `common.save_json(path, data)`
- `common.src_to_record(item_start, item_src_start, src_frame, tl_fps, clip_fps) -> int`
- `common.seconds_to_frames(sec, fps) -> int`
- `common.probe(path) -> {"fps", "frames", "width", "height", "duration", "has_audio"}`
- `common.proxy_for(path) -> Path | None`
- `resolve_util.open_project(project_dir, editor) -> (resolve, pm, project)`
- `resolve_util.timelines(project) -> dict[name, Timeline]`
- `resolve_util.ensure_video_track(timeline, name) -> int`, `ensure_audio_track(timeline, name) -> int`
- `resolve_util.group_map(project) -> dict[file_path, ColorGroup | None]`
- `resolve_util.apply_look(resolve, project, timeline, items, groups) -> int` (Anzahl mit 17 Nodes)
- `resolve_util.reload_count(pm, project, timeline_names, track_names) -> (project, total, ok)`

- [ ] Tests für `src_to_record` (59,94 in 23,976: 600 -> +240), `seconds_to_frames`, `claude_dir`
- [ ] Implementieren, Tests grün, commit

### Task 2: analyse_takes.py

Messung alle 0,25 s auf 320 px Graustufen aus dem Proxy (sonst Original): Schärfe (Laplace-Varianz relativ zum Take und zum Projekt), Bewegung per `cv2.phaseCorrelate` (Reißschwenk = große Verschiebung, Wackler = unruhige Verschiebung), Belichtung relativ zum Take-Median und Anteil ausgebrannter Pixel. Fenster 0,5 s; saubere Abschnitte ab 2 s. Kontaktbild: 4 Takes pro Bild, je Take eine Zeile mit bis zu 6 Bildern aus sauberen Abschnitten, beschriftet mit Key und Sekunde.

- [ ] Tests mit synthetischen Bildern: scharfes Bild ruhig = sauber, Weichzeichner = unscharf, Zitter-Versatz = wackelig, großer Versatz = Schwenk, Segmente unter 2 s entfallen
- [ ] Implementieren, Tests grün
- [ ] Lauf am Demo-Projekt, Laufzeit messen (Ziel < 20 Min. für alle Takes), commit

### Task 3: transcribe.py

faster_whisper `large-v3-turbo` auf CUDA, `vad_filter`, Sprache Deutsch, Wortzeiten. Sprache gilt als vorhanden ab 5 Wörtern mit `no_speech_prob < 0.5`.

- [ ] Lauf am Demo-Projekt, Takes mit Sprache prüfen, commit

### Task 4: place_selects.py + Selects am Demo-Projekt

- Spur `SELECTS` über V1 (vorhanden: wiederverwenden), Platzierung mit `src_to_record`, auf den V1-Clip begrenzt.
- Takes, die auf `SELECTS` schon Clips haben, überspringen.
- Look setzen, Neuladen-Kontrolle, Bericht und Log.
- [ ] Test für Begrenzung und Überspringen (reine Funktion `plan_placements`)
- [ ] Claude wählt Selects aus den Kontaktbildern (+ Transkript), schreibt `selects.json`
- [ ] Lauf, Stichprobe 20 Selects in Resolve: richtige Stelle, keine Unschärfe, Look da; zweiter Lauf überspringt alles; commit

### Task 5: References

- `measure_video.py`: Länge, Schnittzeitpunkte (`scdet`), Schnitte pro Sekunde, Hook-Schnitte in 0–3 s.
- Claude: eigene Exporte der letzten Monate messen, externe Videos über `social_intel` (Instagram, YouTube Shorts) suchen und nach Engagement relativ zur Account-Größe wählen, `REFERENCES.md` schreiben.
- [ ] Test `measure_video` an einem erzeugten Testvideo mit bekannten Schnitten
- [ ] `REFERENCES.md` für das Demo-Briefing, commit

### Task 6: analyse_music.py

librosa: Tempo und Beats, Taktanfang über die stärkste Phase im Viertakt, Abschnitte über Clustering auf taktsynchronen Merkmalen, Energie pro Takt, größter Energiesprung als Drop-Kandidat.

- [ ] Test mit synthetischem 120-BPM-Klick mit betonter Eins: Tempo 120 ± 2, Taktlänge 2,0 s, Phase richtig
- [ ] Implementieren, Tests grün, commit

### Task 7: build_edit.py + Base Edit am Demo-Projekt

- `validate_edit(edit, music_info)` (rein): V1 lückenlos und ohne Überlappung, Länge = Musiklänge, Musikschnitte auf Takten, Quellbereiche im Clip.
- Neue Timeline `<Projekt>_vNN`, Abbruch wenn sie existiert. Spuren `V1`, `ALT 1`, `ALT 2`, Audio `MUSIK`, `O-TON`. Querformat in Hochkant per Zoom füllen. Marker für Grafikplätze. Look auf allen Clips, Neuladen-Kontrolle.
- [ ] Tests für `validate_edit`
- [ ] Artlist-Track zum Briefing wählen und laden, Musik analysieren, Schnittliste schreiben, Lauf, prüfen; commit

### Task 8: place_sound.py + Sound Design am Demo-Projekt

- Kopie `<Projekt>_vNN_SD` per `DuplicateTimeline`, Abbruch wenn sie existiert. Audiospuren `SFX`, `ATMO`. Dateien unter `ASSETS\SFX`, Bin `SOUND DESIGN`. Fester Pegel `level_db`.
- [ ] Test `validate_sound`
- [ ] Sound-Liste schreiben (Kamera-Ton, Artlist-SFX), Lauf, Original-Version unverändert prüfen; commit

### Task 9: Skill-Anleitungen und Gesamttest

- [ ] `selects.md`, `references.md`, `base-edit.md`, `sound-design.md`, `craft-editing.md`, `craft-sound.md`; Tabelle in `SKILL.md` aktualisieren
- [ ] Frischer Agent: je eine Anfrage pro Unterfunktion routet richtig (nur lesen)
- [ ] README im Repo, Obsidian-Notizen, push
