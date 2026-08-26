# Betriebs-, Benutzer- und Technikhandbuch

## Bedienung und uMap-Ablauf

Unternehmen werden über PPS-Nummern eindeutig identifiziert, können mehrere Gewerke und je Gewerk andere Gebiete haben. Deaktivieren ist dem endgültigen Löschen vorzuziehen. Beim Export wird bewusst genau ein aktives Gewerk gewählt. Danach in uMap die gleichnamige Ebene öffnen, deren bisherige Inhalte entfernen, die neue Datei importieren, Karte speichern und kontrollieren. Empfohlene Suchfelder: `gebiet,firmen,pps_nummern,dienstleister`.

## Datenmodell

SQLite speichert `unternehmen`, `gewerke`, den n:m-Bezug `unternehmen_gewerke`, `gebiete`, dreiteilige `gebietszuordnungen` sowie `export_protokoll`. Fremdschlüssel, Eindeutigkeitsbedingungen und Transaktionen verhindern verwaiste beziehungsweise doppelte Zuordnungen. Geometrien werden als GeoJSON in `gebiete.geometrie` abgelegt.

Beim erstmaligen Anlegen der Datenbank werden die detailreichen Gebietsdateien `gebiete/plz_2_gebiete.geojson` und `gebiete/luxemburg.json` eingelesen. Der Deutschland-Datensatz verwendet `properties.plz`, der Luxemburg-Datensatz `properties.gebiet`; beide Varianten werden vom Gebietslader unterstützt.

## Sicherung

Sicherungen tragen einen Zeitstempel. Vor jeder Wiederherstellung erstellt der Service automatisch eine Vorsicherung. Die Oberfläche muss vor dem Ersetzen des Bestands eine Bestätigung abfragen.

## GeoJSON

Der Export gruppiert aktive Unternehmen nach Gebiet, sortiert sie stabil nach Name und gibt jede Geometrie einmal aus. Eigenschaften sind `gebiet`, `gewerk`, `firmen`, `pps_nummern`, `dienstleister` und `anzahl_dienstleister`. Darstellungseigenschaften bleiben Sache der uMap-Ebene.

## Windows-Build

In einer Windows-Eingabeaufforderung:

```text
py -m venv .venv
.venv\Scripts\pip install -e ".[test,build]"
.venv\Scripts\pytest
.venv\Scripts\pyinstaller --noconfirm --windowed --name Dienstleisterkarten --collect-all PySide6 app/main.py
```

Die Ordner `gebiete`, `daten`, `exporte` und `sicherungen` neben dem Auslieferungspaket bereitstellen. Der produktive Datenordner liegt standardmäßig in `%LOCALAPPDATA%` und bleibt bei Updates erhalten.

## Test- und Übergabehinweis

`pytest` prüft Importzusammenführung, führende Nullen, Duplikate, Konflikte, das Laden der detailreichen Grenzgeometrien, gruppierten Einzel-Export, Inaktivfilter, Dateinamen sowie Sicherung/Wiederherstellung. Vor Abnahme ist ein Testimport in die eingesetzte uMap-Version durchzuführen.
