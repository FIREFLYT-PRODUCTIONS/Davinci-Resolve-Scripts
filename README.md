# FIREFLYT DaVinci Resolve Scripts

Vom kopierten Shoot zum fertigen Resolve-Projekt. Läuft auf Windows.

## Benutzen

1. Projektordner anlegen: `Z:\2026\NN - KUNDE\2026-MM-DD_KUNDE_PROJEKT` (Vorlage in `Z:\00 - BASE FOLDERS`).
2. Shoot-Dateien nach `01 - SOURCE` kopieren.
3. Projektordner auf `PROJEKT_SETUP.bat` ziehen oder die Datei doppelklicken.
4. Conrad oder Felix wählen, Prüfung lesen, **Starten**.

Bei einem Neukunden wird Resolve einmal beendet und neu gestartet. Der Kundenordner muss dafür schon `00 - DAVINCI RESOLVE PROJECTS` enthalten (Vorlage `00 - CUSTOMER`).

Am Ende gibt es:

- die Kunden-Library in Resolve (`NN - KUNDE` bzw. `NN - KUNDE - FELIX`)
- das Projekt aus dem Base-Template, benannt wie der Projektordner
- alle Medien unter `00 - SOURCE`, Source-Timelines, Clipfarben und FPS-Flags
- Color Groups pro Clip und den `BASE NODE TREE` auf allen Clips
- den laufenden Proxy Generator. Er rechnet im Hintergrund weiter und bleibt offen, mit den Originaldateien kann sofort gearbeitet werden. Fertige Proxys verknüpft Resolve selbst.

Das Log liegt im Projektordner unter `00 - CONRAD\PROJECT` bzw. `00 - FELIX\PROJECT`.

Läuft der Generator schon für einen anderen Shoot, wird er nicht angefasst: Das Setup läuft durch und nennt den Ordner, der dort mit **Add** hinzuzufügen ist.

Gibt es das Projekt schon, bietet das Fenster an, nur Fehlendes zu ergänzen. Vorhandenes bleibt unverändert. Neue Clips einer Kamera, die schon eine Timeline hat, landen im Bin, aber nicht in der Timeline; das Setup weist darauf hin.

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

## Kameras

Die Kamera kommt aus den Metadaten der Datei, das Bildprofil pro Clip. Neue Kameras werden in `BASE_PROJECT_SETUP.py` unter `CLIP_COLORS` und `MODEL_NAMES` eingetragen.

| Kamera | Clipfarbe | Color Group |
|---|---|---|
| Sony FX3 | Orange (FX3-2: Apricot) | `S-LOG 3`, wenn der Clip S-Log3 ist, sonst keine |
| Sony A7IV | Yellow (A7IV-2: Lime) | wie FX3 |
| Sony A7V | Green | wie FX3 |
| DJI Mavic 3 Pro | Tan | Hasselblad `D-LOG`, Tele `D-LOG M` |
| DJI Mavic 4 Pro | Brown | `D-LOG M` |
| DJI Mini 4 Pro | Beige | `D-LOG M` |
| DJI Mini 5 Pro | Chocolate | `D-LOG M` |
| DJI Avata 2 | Olive | `D-LOG M` |
| GoPro HERO 11 | Navy | `GP-LOG` nur bei GP-Log, Flat und Standard ohne |
| GoPro HERO 13 | Teal | wie HERO 11 |

DJI schreibt das Farbprofil nicht lesbar in die Datei. Erreicht mindestens ein Viertel der Clips einer Kamera das hellste Weiß, gilt sie im Shoot als nicht in Log gefilmt: keine Gruppe, dafür ein Hinweis. Dafür braucht es `ffmpeg` auf dem Rechner, ohne wird nicht gemessen.

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
