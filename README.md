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

## Entwicklung

```bash
pip install -e '.[test]'
pytest
```

Die enthaltenen Flächen sind ein kleiner, schematischer Offline-Demodatensatz und **keine amtlichen Grenzgeometrien**. Vor Produktion sind die Dateien unter `gebiete/` durch fachlich freigegebene GeoJSON-FeatureCollections mit `properties.gebiet` zu ersetzen.

Weitere Übergabeinformationen stehen in [`dokumentation/handbuch.md`](dokumentation/handbuch.md).
