# Betriebs-, Benutzer- und Technikhandbuch

## Bedienung

Unternehmen werden über PPS-Nummern eindeutig identifiziert, können mehrere Gewerke und je Gewerk andere Gebiete haben. In der Unternehmensliste öffnet **Neu**, **Bearbeiten** oder ein Doppelklick den Editor. Die Zuordnungen werden zeilenweise im Format `Gewerk: 04, 06, LUX` eingegeben. Erst **Speichern** und die anschließende Bestätigung übernehmen Änderungen. Deaktivieren ist dem endgültigen Löschen vorzuziehen. Eine eigene Gewerke-, Export- oder Sicherungsseite ist nicht Bestandteil der Oberfläche.

## Datenmodell

SQLite speichert `unternehmen`, `gewerke`, den n:m-Bezug `unternehmen_gewerke`, `gebiete`, dreiteilige `gebietszuordnungen` sowie `export_protokoll`. Fremdschlüssel, Eindeutigkeitsbedingungen und Transaktionen verhindern verwaiste beziehungsweise doppelte Zuordnungen. Geometrien werden als GeoJSON in `gebiete.geometrie` abgelegt.

Beim erstmaligen Anlegen der Datenbank werden die detailreichen Gebietsdateien `gebiete/plz_2_gebiete.geojson` und `gebiete/luxemburg.json` eingelesen. Der Deutschland-Datensatz verwendet `properties.plz`, der Luxemburg-Datensatz `properties.gebiet`; beide Varianten werden vom Gebietslader unterstützt.

## Windows-Build

In einer Windows-Eingabeaufforderung:

```text
py -m venv .venv
.venv\Scripts\pip install -e ".[test,build]"
.venv\Scripts\pytest
.venv\Scripts\pyinstaller --noconfirm --windowed --name Dienstleisterkarten --collect-all PySide6 app/main.py
```

Die Ordner `gebiete` und `daten` neben dem Auslieferungspaket bereitstellen. Der produktive Datenordner liegt standardmäßig in `%LOCALAPPDATA%` und bleibt bei Updates erhalten.

## Test- und Übergabehinweis

`pytest` prüft unter anderem Importzusammenführung, führende Nullen, Duplikate, Konflikte, das Laden der detailreichen Grenzgeometrien sowie die Bestandsliste und deren Editor.
