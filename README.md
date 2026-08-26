# Dienstleisterkarten

Lokale, deutschsprachige Windows-Anwendung zur Pflege von Dienstleistern und zum Export **genau eines Gewerks** als gruppiertes GeoJSON. Python 3.11+, PySide6, SQLite und pytest; keine Serververbindung.

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

Eine vorhandene Datenbank wird abgelehnt. Nur für eine bewusst wiederholte Entwicklungsübernahme ist `--ueberschreiben` vorgesehen. Bei fachlichen Fehlern wird keine Zieldatenbank veröffentlicht.

Bei der Platzhalter-PPS-Nummer `0` unterscheidet der Import Unternehmen zusätzlich anhand ihres Namens, sodass diese Datensätze vollständig erhalten bleiben und nicht fälschlich zusammengeführt werden. Für alle anderen PPS-Nummern bleibt die Eindeutigkeitsprüfung bestehen. Die nicht vergebenen deutschen PLZ-2-Bereiche `05`, `11`, `43` und `62` werden übersprungen, weil dafür keine geografische Fläche existiert; alle übrigen Zuordnungen derselben Firma werden weiterhin importiert.

## Entwicklung

```bash
pip install -e '.[test]'
pytest
```

Die Anwendung lädt die detailreichen Offline-Geometrien aus `gebiete/plz_2_gebiete.geojson` und `gebiete/luxemburg.json`. Gebietsschlüssel werden dabei aus `properties.plz` beziehungsweise `properties.gebiet` übernommen.

Weitere Übergabeinformationen stehen in [`dokumentation/handbuch.md`](dokumentation/handbuch.md).
