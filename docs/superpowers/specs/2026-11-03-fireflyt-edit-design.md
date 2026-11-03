# fireflyt-edit – Design

Stand: 2026-11-03, abgestimmt mit Conrad

## Ziel

Ein Claude-Skill, der ein FIREFLYT-Projekt vom befüllten Projektordner bis zur ersten geschnittenen Version mit Sound Design begleitet. Er ersetzt den Skill `fireflyt-projekt-setup`.

Fünf Unterfunktionen, einzeln aufrufbar, in dieser Reihenfolge aufeinander aufbauend:

1. **Setup** – Resolve-Projekt anlegen (vorhandenes `PROJEKT_SETUP.py`)
2. **Selects** – gute Momente jedes Takes auf eine Spur über dem Original legen
3. **References** – aktuelle erfolgreiche Videos zum Briefing finden und auswerten
4. **Base Edit** – erste Schnittversion auf den vorgegebenen Musik-Track
5. **Sound Design** – Effekte und Atmo zu einer Schnittversion

## Aufbau des Skills

```
C:\Users\conra\.claude\skills\fireflyt-edit\
  SKILL.md                 Einstieg: Erkennen der Unterfunktion, gemeinsame Regeln
  references\
    setup.md               Ablauf Setup (Inhalt des alten Skills)
    selects.md
    references.md
    base-edit.md
    sound-design.md
    craft-editing.md       Schnitt-Handwerk, destilliert aus beat-sync-editing und editing-montage
    craft-sound.md         Sound-Handwerk, destilliert aus sound-effects und audio-mixing-mastering
```

Hilfsskripte liegen im Repo `Davinci-Resolve-Scripts` neben `PROJEKT_SETUP.py`, damit sie versioniert sind und wie das Setup auch ohne Claude laufen:

```
SCRIPS\edit\
  resolve_util.py          Verbindung, Timeline finden, Node Tree und Color Group auf neue Clips
  analyse_takes.py         Technik-Durchlauf und Kontaktbilder pro Take
  transcribe.py            Transkript mit faster_whisper (lokal, GPU)
  place_selects.py         selects.json auf die Spur SELECTS legen
  build_edit.py            Schnittliste (JSON) als neue Timeline-Version bauen
  analyse_music.py         Takt, Beats, Abschnitte mit librosa
  place_sound.py           Sound-Liste (JSON) auf SFX/ATMO-Spuren einer Kopie legen
```

Fremde Skills werden nicht installiert. Ihr Inhalt wird einmal gelesen, der Code geprüft, und das Fachwissen in `craft-*.md` übernommen.

## Gemeinsame Regeln

- **Claude-Ordner pro Editor:** `<Projekt>\00 - CONRAD\CLAUDE\` bzw. `00 - FELIX\CLAUDE\`, beim ersten Gebrauch angelegt:
  - `BRIEFING.md`, `REFERENCES.md`
  - `SELECTS\selects.json`
  - `EDIT\vNN.md` und `EDIT\vNN.json`
  - `SOUND\vNN.md` und `SOUND\vNN.json`
  - `LOGS\`
- **Briefing:** eine Datei pro Projekt, ergänzt um Kunde und Deliverables aus dem FIREFLYT-CRM. Fehlt sie, fragt der Skill einmal nach und legt sie an.
- **Nichts überschreiben:** Source-Timelines bekommen nur die Spur `SELECTS` dazu. Base Edit legt immer eine neue Version an, Sound Design arbeitet auf einer Kopie (`_SD`).
- **Neue Timeline-Clips** bekommen immer `BASE NODE TREE` und die Color Group des Media-Pool-Clips.
- **Bestehende Nutzerregeln:**
  - Musik nur roh schneiden, kein Ducking
  - keine Exporte ohne ausdrücklichen Auftrag
  - unsichere Shot-Wahl als Alternativen auf `ALT 1` und `ALT 2`
  - kein Schlusspunkt in Grafiken
  - nur Material des aktuellen Kunden verwenden
- **Kundenmaterial bleibt lokal:** Analyse mit `ffmpeg`, `opencv` und `faster_whisper` auf dem Rechner, kein Upload zu Drittdiensten.
- **Vorhandene Werkzeuge:** Python 3.14, `ffmpeg` 9 (`blurdetect`, `vidstabdetect`, `scdet`, `signalstats`), `opencv`, `librosa`, `faster_whisper`, RTX 4080.

## 1. Setup

Inhalt des bisherigen Skills, unverändert im Verhalten:

1. Ordner aus der Beschreibung des Nutzers unter `Z:\2026` finden, bei mehreren Treffern nachfragen.
2. Probelauf zusammenfassen.
3. Nur bei Neukunde, offenem Projekt oder vorhandenem Projekt nachfragen.
4. Lauf im Hintergrund.
5. Hinweise als Handlungen melden.

Antwortet Resolve nicht, bietet der Skill einen Neustart von Resolve an.

**Änderung am Skript:** Das Log wandert von `00 - <EDITOR>\PROJECT` nach `00 - <EDITOR>\CLAUDE\LOGS`.

## 2. Selects

- **Eingabe:** alle Source-Timelines, oder vom Nutzer genannte.
- **Technik-Durchlauf:**
  - Liest die Proxys, falls vorhanden, sonst die Originale.
  - Misst etwa alle 0,5 s Unschärfe, Wackler, Reißschwenks und Belichtung, die Belichtung relativ zum Take wegen Log.
  - Ergebnis sind die technisch sauberen Abschnitte. Unscharfes oder Wackeliges ist nie ein Select.
- **Bild-Durchlauf:**
  - Kontaktbild pro Take aus den sauberen Abschnitten, mit Zeitstempeln. Claude wählt nach Motiv, Bildaufbau und Moment.
  - Pro Take alle wirklich guten Momente, je etwa 2 bis 10 s.
  - Bei Sprache mit Transkript, Schnitt an Satzgrenzen.
- **Ablage:** `SELECTS\selects.json` mit Datei, Start, Ende (Frames der Quelle), Bewertung, Grund und Bildinhalt in Stichworten. Den Bildinhalt nutzt Sound Design.
- **Resolve:**
  - Spur `SELECTS` über V1. Jeder Select liegt über seiner Originalstelle: `recordFrame` = Position des V1-Clips + (Select-Start − Quell-Start des V1-Clips).
  - Node Tree und Color Group wie bei V1.
- **Wiederholung:** Takes mit Selects werden übersprungen.
- **Bericht:** Selects pro Timeline sowie verworfene Takes mit Grund.

## 3. References

- **Eingabe:** Briefing, Anzahl (Standard 8), optional Accounts oder Beispiele.
- **Eigene Videos:**
  - Exporte der letzten Monate aus `02 -DELIVERABLES\VIDEOS` und `EXPORT` aller Projekte, lokal analysiert.
  - Zahlen des FIREFLYT-Instagram-Accounts über `social_intel`.
  - Nur als Stil-Vorlage, nie als Material.
- **Extern:**
  - Instagram, TikTok, YouTube Shorts (bei 16:9 YouTube) über `social_intel`, standardmäßig die letzten 3 Monate.
  - Breit suchen, dann nach Engagement im Verhältnis zur Account-Größe auswählen, mit Vielfalt bei Hooks und Stilen.
- **Analyse pro Video:**
  - Link, Account, Datum und Kennzahlen
  - Länge und Hook (0 bis 3 s)
  - Schnitte pro Sekunde und Tempowechsel
  - Aufbau, Text und Ton
  - Grund für die Auswahl
- **Ablage:** `REFERENCES.md`, oben die gemeinsamen Muster, dann die Teile „Eigene“ und „Extern“.
- **Grenze:** kein Zugriff auf Trending-Seiten. „Trend“ heißt aktuell und überdurchschnittlich erfolgreich.

## 4. Base Edit

- **Eingabe:** Briefing, die Muster aus `REFERENCES.md`, `selects.json` und der Musik-Track des Nutzers (Pflicht). Länge und Format aus dem Briefing oder vom Nutzer.
- **Musik:** Takt, Beats und Abschnitte mit `librosa`. Musikschnitt auf die Ziellänge nur auf Taktgrenzen, roh.
- **Dramaturgie:** Ablauf mit Abschnitten (Hook, Ankommen, Aufbau, Höhepunkt, Ende mit Logo-Platz) und Schnittrhythmus pro Abschnitt aus den References.
- **Shot-Wahl:**
  - nach der Funktion im Ablauf
  - Match Cuts, keine Sprünge zwischen ähnlichen Einstellungen, Bewegungsrichtung halten
  - Speaker in Echtzeit
  - Alternativen auf `ALT 1` und `ALT 2`
- **Resolve:** neue Timeline `<Projekt>_vNN` im Zielformat, Node Tree und Color Group auf allen Clips. Eine vorhandene Version wird nie verändert.
- **Ablage:** `EDIT\vNN.json` (Schnittliste) und `EDIT\vNN.md` (Ablauf, Begründung, Stellen mit Alternativen, Plätze für Grafiken).
- **Nicht enthalten:** Grafiken, Color über den Node Tree hinaus, Exporte.

## 5. Sound Design

- **Eingabe:** eine Version `vNN`, Briefing und Musik.
- **Plan:**
  - **Effekte:** Whoosh auf schnelle Schnitte und Reißschwenks, Riser vor dem Drop, Hit auf dem Drop, sparsame Akzente bei Bewegungen im Bild.
  - **Atmo:** pro Abschnitt eine durchgehende Fläche passend zum Ort.
- **Quellen, in dieser Reihenfolge:**
  1. brauchbarer Originalton der Kamera
  2. Artlist-SFX-Katalog
  3. lizenzfreie Effekte
- **Resolve:**
  - Kopie `<Projekt>_vNN_SD`, Spuren `SFX` und `ATMO`, framegenau gesetzt.
  - Fester leiser Grundpegel. Kein Mix und kein Ducking, das macht der Nutzer.
  - Dateien unter `ASSETS\SFX`.
- **Ablage:** `SOUND\vNN.json` und `SOUND\vNN.md` mit Zeitpunkt, Datei, Quelle und Grund.

## Prüfen beim Bau

- `AppendToTimeline` mit `trackIndex` und `recordFrame` auf einer zusätzlichen Spur, auch bei Clips mit anderer Framerate als die Timeline
- Node Tree und Color Group auf per Skript angelegten Clips, nach Neuladen kontrolliert wie im Setup
- Artlist-SFX: Download und Lizenz im bestehenden Abo
- Laufzeit Selects: Ziel unter 20 Min. für 124 Takes, gemessen beim ersten echten Lauf
- Code der vier Fremd-Skills vor dem Destillieren lesen

## Tests

- Jede Unterfunktion zuerst an einer Kopie eines echten Projekts in einem Testkunden, danach Testkunde und Library entfernen
- **Selects:** Stichprobe von 20 Takes von Hand prüfen. Kein unscharfer oder wackeliger Select, jeder Select an der richtigen Stelle über V1.
- **Base Edit:** Schnitte liegen auf den Beats, die Länge stimmt, Alternativen liegen auf `ALT 1` und `ALT 2`, keine bestehende Timeline verändert.
- **Sound Design:** Effekte framegenau an den geplanten Stellen, Original-Version unverändert.

## Nicht im Umfang

- Grafiken und Bauchbinden (bleibt bei Remotion und Fusion)
- Color Grading über den Base Node Tree hinaus
- Exporte und Delivery
- Revision, also Kundenfeedback in eine neue Version, als mögliche spätere Unterfunktion
