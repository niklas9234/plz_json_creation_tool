import json
from pathlib import Path
from app.datenbank import Database


GEBIETSDATEIEN = ("plz_2_gebiete.geojson", "luxemburg.json")


def ausgelieferte_gebietsdateien(root: Path | None = None) -> list[Path]:
    """Gibt die detailreichen, mit der Anwendung ausgelieferten Geodaten zurück."""
    basis = root or Path(__file__).resolve().parents[2]
    return [basis / "gebiete" / name for name in GEBIETSDATEIEN]


def lade_gebiete(db: Database, dateien: list[Path]) -> int:
    """Lädt FeatureCollections mit Gebietsschlüsseln in ``gebiet`` oder ``plz``."""
    count = 0
    with db.connect() as con:
        for path in dateien:
            doc = json.loads(Path(path).read_text(encoding="utf-8"))
            if doc.get("type") != "FeatureCollection": raise ValueError(f"{path.name} ist keine GeoJSON-FeatureCollection.")
            for feature in doc.get("features", []):
                props = feature.get("properties", {})
                key = str(props.get("gebiet") or props.get("plz") or "").strip().upper()
                geometry = feature.get("geometry")
                if not key or not geometry: raise ValueError(f"In {path.name} fehlt ein Gebietsschlüssel oder eine Geometrie.")
                typ = props.get("typ", "LAND" if not key.isdigit() else "PLZ2")
                anzeigename = props.get("anzeigename") or props.get("name") or (f"PLZ-2 {key}" if key.isdigit() else key)
                con.execute("INSERT INTO gebiete(schluessel,anzeigename,typ,geometrie,label_lon,label_lat) VALUES (?,?,?,?,?,?) ON CONFLICT(schluessel) DO UPDATE SET anzeigename=excluded.anzeigename,typ=excluded.typ,geometrie=excluded.geometrie,label_lon=excluded.label_lon,label_lat=excluded.label_lat",
                    (key, anzeigename, typ, json.dumps(geometry), props.get("label_lon"), props.get("label_lat")))
                count += 1
    return count
