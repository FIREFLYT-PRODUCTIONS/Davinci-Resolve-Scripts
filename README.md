# FIREFLYT DaVinci Resolve Scripts

Vom kopierten Shoot zum fertigen Resolve-Projekt. Läuft auf Windows.

## Benutzen

1. Projektordner anlegen: `Z:\2026\NN - KUNDE\2026-MM-DD_KUNDE_PROJEKT` (Vorlage in `Z:\00 - BASE FOLDERS`).
2. Shoot-Dateien nach `01 - SOURCE` kopieren.
3. Projektordner auf `PROJEKT_SETUP.bat` ziehen oder die Datei doppelklicken.
4. Conrad oder Felix wählen, Prüfung lesen, **Starten**.

Bei einem Neukunden wird Resolve einmal beendet und neu gestartet. Der Kundenordner muss dafür schon `00 - DAVINCI RESOLVE PROJECTS` enthalten (Vorlage `00 - CUSTOMER`).

Antwortet ein vom Setup gestartetes Resolve nicht, startet das Setup es einmal selbst neu. Ein Resolve, das schon vorher offen war, beendet es nie.

Am Ende gibt es:

- die Kunden-Library in Resolve (`NN - KUNDE` bzw. `NN - KUNDE - FELIX`)
- das Projekt aus dem Base-Template, benannt wie der Projektordner
- alle Medien unter `00 - SOURCE`, Source-Timelines, Clipfarben und FPS-Flags
- Color Groups pro Clip und den `BASE NODE TREE` auf allen Clips
- den laufenden Proxy Generator. Er rechnet im Hintergrund weiter und bleibt offen, mit den Originaldateien kann sofort gearbeitet werden. Fertige Proxys verknüpft Resolve selbst.

Das Log liegt im Projektordner unter `00 - CONRAD\CLAUDE\LOGS` bzw. `00 - FELIX\CLAUDE\LOGS`.

Läuft der Generator schon für einen anderen Shoot, wird er nicht angefasst: Das Setup läuft durch und nennt den Ordner, der dort mit **Add** hinzuzufügen ist.

Gibt es das Projekt schon, bietet das Fenster an, nur Fehlendes zu ergänzen. Vorhandenes bleibt unverändert: Clipfarben, Flags, Color Groups, Grades und das Projektformat werden nicht angefasst. Neue Clips einer Kamera, die schon eine Timeline hat, landen im Bin, aber nicht in der Timeline; das Setup weist darauf hin.

Ist der Library-Name in Resolve schon mit einem anderen Pfad registriert (z.B. altes Laufwerk), bricht schon die Prüfung ab, bevor etwas geändert wird.

Vor jeder Änderung an `dblist.conf` und an der INI des Proxy Generators legt das Setup eine Sicherung an: `%APPDATA%\FIREFLYT\projekt_setup_backups`.

## Dateien

| Datei | Zweck |
|---|---|
| `PROJEKT_SETUP.bat` | Startet das Fenster, prüft ob Python da ist |
| `PROJEKT_SETUP_GUI.pyw` | Das Fenster |
| `PROJEKT_SETUP.py` | Gesamtablauf, auch per Kommandozeile nutzbar |
| `BASE_PROJECT_SETUP.py` | Timelines, Farben, Flags und Gruppen. Läuft auch allein aus der Resolve-Konsole |

```
python PROJEKT_SETUP.py "<Projektordner>" [--editor FELIX] [--dry-run] [--no-proxies] [--resume] [--close-open]
```

Exit-Codes: `0` sauber, `1` fertig mit Hinweisen, `2` Abbruch, `3` anderes Projekt offen, `4` Projekt existiert schon.

## Edit: vom Projekt zur ersten Version

Die Skripte in `edit\` führen ein aufgesetztes Projekt bis zur ersten Schnittversion mit Sound Design. Gedacht sind sie für den Claude-Skill `fireflyt-edit`: Claude trifft die Auswahl und schreibt sie als JSON, die Skripte messen und schreiben in Resolve. Sie laufen auch ohne Claude, wenn die JSON-Dateien da sind. Alles liegt in `<Projekt>\00 - <EDITOR>\CLAUDE\`.

| Schritt | Skript | Liest | Schreibt |
|---|---|---|---|
| Takes messen | `analyse_takes.py` | Videos in `01 - SOURCE` | `SELECTS\takes.json`, Kontaktbilder |
| Sprache | `transcribe.py` | `takes.json` | `SELECTS\transcripts.json` |
| Selects umrechnen | `make_selects.py` | `SELECTS\selects_draft.json` | `SELECTS\selects.json` |
| Selects setzen | `place_selects.py` | `selects.json` | Spur `SELECTS` in den Source-Timelines |
| References messen | `measure_video.py` | eigene Exporte | Länge, Schnitte pro Sekunde |
| Musik messen | `analyse_music.py` | Musikdatei | `EDIT\music_<name>.json` |
| Base Edit | `build_edit.py` | `EDIT\vNN.json` | Timeline `<Projekt>_vNN` |
| Sound Design | `place_sound.py` | `SOUND\vNN.json` | Kopie `<Projekt>_vNN_SD` |

```
python edit\build_edit.py "<Projektordner>" v01 [--editor FELIX] [--check]
python edit\place_sound.py "<Projektordner>" v01 [--editor FELIX] [--check]
```

`--check` prüft nur die JSON-Datei, ohne Resolve. Exit-Codes wie beim Setup, `4` heißt hier: die Version bzw. die Kopie gibt es schon. Vorhandenes wird nie verändert. Source-Timelines bekommen nur die Spur `SELECTS` dazu, jeder Base Edit ist eine neue Timeline, Sound Design eine Kopie. Neue Clips bekommen `BASE NODE TREE` und die Color Group. Exportiert wird nichts.

Tests ohne Resolve: `python -m unittest discover -s edit\tests`. Bauplan und JSON-Formate: `docs\superpowers\plans\2026-11-03-fireflyt-edit.md`.

Zusätzlich gebraucht: `numpy`, `opencv-python`, `librosa`, `faster-whisper` (CUDA für die Transkription).

## Kameras

Die Kamera kommt aus den Metadaten der Datei, das Bildprofil pro Clip. Neue Kameras werden in `BASE_PROJECT_SETUP.py` unter `CLIP_COLORS` und `MODEL_NAMES` eingetragen.

| Kamera | Clipfarbe | Color Group |
|---|---|---|
| Sony FX3 | Orange (FX3-2: Apricot) | `S-LOG 3`, wenn der Clip S-Log3 ist, sonst keine |
| Sony A7IV | Yellow (A7IV-2: Lime) | wie FX3 |
| Sony A7V | Green | wie FX3 |
| DJI Mavic 3 Pro | Tan | Hasselblad `D-LOG`, Tele `D-LOG M` |
| DJI Mavic 4 Pro | Brown | `D-LOG M`, bei gemessen sehr flachem Bild `D-LOG` |
| DJI Mini 4 Pro | Beige | `D-LOG M` |
| DJI Mini 5 Pro | Chocolate | `D-LOG M` |
| DJI Avata 2 | Olive | `D-LOG M` |
| GoPro HERO 11 | Navy | `GP-LOG` nur bei GP-Log, Flat und Standard ohne |
| GoPro HERO 13 | Teal | wie HERO 11 |

DJI schreibt das Farbprofil nicht lesbar in die Datei. Die Mavic 3 kann D-Log nur auf der Hasselblad, das Objektiv steht in der Datei. Bei der Mavic 4 können alle Kameras D-Log, deshalb wird pro Objektiv gemessen: Liegt das hellste Weiß im Median unter 780 (10 Bit), gilt es als D-Log, sonst als D-Log M. Der Wert stammt von der Mavic 3, mit echtem D-Log der Mavic 4 ist er noch nicht geprüft.

Erreicht mindestens ein Viertel der Clips einer Drohne das hellste Weiß, kommt ein Hinweis, die Gruppe bleibt aber. Für beide Messungen braucht es `ffmpeg`; ohne bleibt es beim Standard.

FPS-Flags: Green bis 30 fps, Yellow bis 99 fps, Red ab 100 fps.

## Voraussetzungen

- DaVinci Resolve Studio, in den Einstellungen External Scripting auf Local
- Python 3 im PATH
- `Z:` verbunden
- die Korrektur-LUTs unter `00 - MY LUTS\CORRECTION LUTS`
- empfohlen: `ffmpeg` im PATH

## Grenzen

- Resolve kann per API keine Library anlegen. Das Setup trägt sie in `dblist.conf` ein, dafür muss Resolve kurz zu.
- Der Proxy Generator hat keine Schnittstelle. Das Setup setzt seinen Überwachungsordner in der INI und drückt Start über Windows UI Automation. Ein Resolve-Update kann das brechen.
- Das `.drp` in `Z:\00 - BASE FOLDERS\BASE_PROJECTS` wird nicht verwendet. Die Quelle ist die Library `00 - BASE PROJECT TEMPLATE`.
