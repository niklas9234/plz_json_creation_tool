# Dienstleisterkarten

Lokale, deutschsprachige Windows-Anwendung zur Pflege von Dienstleistern. Python 3.11+, PySide6, SQLite und pytest; keine Serververbindung.

Unternehmen lassen sich in der Bestandsliste neu anlegen oder bearbeiten. Änderungen werden erst über **Speichern** vorgemerkt und anschließend nach einer ausdrücklichen Rückfrage übernommen. Eine eigene Gewerke-, Export- oder Sicherungsseite gibt es nicht.

## Schnellstart

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
dienstleisterkarten
```

Der beschreibbare Bestand liegt unter `%LOCALAPPDATA%\Dienstleisterkarten`; eine Installation überschreibt ihn nicht. Für Entwicklung und Tests kann `DIENSTLEISTERKARTEN_HOME` gesetzt werden.

## Einmaliger Import

Eine kontrollierte CSV mit exakt `Gewerk;Unternehmen;PPS_Nummer;PLZ` nach `initial_import/input/` legen. Dann:

```bash
dienstleisterkarten-import --datenbank daten/dienstleister.db
```

Eine von der App lediglich mit Gebietsgeometrien initialisierte, ansonsten leere Datenbank kann direkt befüllt werden. Enthält sie bereits Unternehmen oder Gewerke, wird sie abgelehnt; für einen bewusst vollständigen Neuimport ist `--ueberschreiben` erforderlich. Bei fachlichen Fehlern wird keine Zieldatenbank veröffentlicht. Die Konsolenausgabe nennt CSV- und Datenbankpfad sowie eindeutig `ERFOLGREICH` oder `NICHT IMPORTIERT`.

Bei der Platzhalter-PPS-Nummer `0` unterscheidet der Import Unternehmen zusätzlich anhand ihres Namens, sodass diese Datensätze vollständig erhalten bleiben und nicht fälschlich zusammengeführt werden. Für alle anderen PPS-Nummern bleibt die Eindeutigkeitsprüfung bestehen. Die nicht vergebenen deutschen PLZ-2-Bereiche `05`, `11`, `43` und `62` werden übersprungen, weil dafür keine geografische Fläche existiert; alle übrigen Zuordnungen derselben Firma werden weiterhin importiert.

## Entwicklung

```bash
pip install -e '.[test]'
pytest
```

Die Anwendung lädt die detailreichen Offline-Geometrien aus `gebiete/plz_2_gebiete.geojson` und `gebiete/luxemburg.json`. Gebietsschlüssel werden dabei aus `properties.plz` beziehungsweise `properties.gebiet` übernommen.

Weitere Übergabeinformationen stehen in [`dokumentation/handbuch.md`](dokumentation/handbuch.md).


## Alternative: Datenbank manuell vollständig löschen

```bash
Remove-Item "$env:LOCALAPPDATA\Dienstleisterkarten\daten\dienstleister.db"
```
