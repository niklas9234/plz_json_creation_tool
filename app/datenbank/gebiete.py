import json
from pathlib import Path
from app.datenbank import Database


def lade_gebiete(db: Database, dateien: list[Path]) -> int:
    """Lädt ausgelieferte FeatureCollections; Schlüssel steht in properties.gebiet."""
    count = 0
    with db.connect() as con:
        for path in dateien:
            doc = json.loads(Path(path).read_text(encoding="utf-8"))
            if doc.get("type") != "FeatureCollection": raise ValueError(f"{path.name} ist keine GeoJSON-FeatureCollection.")
            for feature in doc.get("features", []):
                props = feature.get("properties", {}); key = str(props.get("gebiet", "")).strip().upper()
                geometry = feature.get("geometry")
                if not key or not geometry: raise ValueError(f"In {path.name} fehlt ein Gebietsschlüssel oder eine Geometrie.")
                typ = props.get("typ", "LAND" if not key.isdigit() else "PLZ2")
                con.execute("INSERT INTO gebiete(schluessel,anzeigename,typ,geometrie,label_lon,label_lat) VALUES (?,?,?,?,?,?) ON CONFLICT(schluessel) DO UPDATE SET anzeigename=excluded.anzeigename,typ=excluded.typ,geometrie=excluded.geometrie,label_lon=excluded.label_lon,label_lat=excluded.label_lat",
                    (key, props.get("anzeigename", key), typ, json.dumps(geometry), props.get("label_lon"), props.get("label_lat")))
                count += 1
    return count
