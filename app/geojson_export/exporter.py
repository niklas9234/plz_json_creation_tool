from __future__ import annotations
import json, re, unicodedata
from dataclasses import dataclass
from pathlib import Path
from app.datenbank import Database


def dateiname_fuer_gewerk(name: str) -> str:
    text = name.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss").replace("&", " und ")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return f"{text or 'gewerk'}.geojson"


@dataclass(frozen=True)
class ExportVorschau:
    gewerk: str; aktive_unternehmen: int; gebiete: int; dateiname: str


class GeoJSONExporter:
    def __init__(self, db: Database): self.db = db
    def vorschau(self, gewerk_id: int) -> ExportVorschau:
        with self.db.connect() as con:
            g = con.execute("SELECT name FROM gewerke WHERE id=? AND aktiv=1", (gewerk_id,)).fetchone()
            if not g: raise ValueError("Das ausgewählte Gewerk ist nicht vorhanden oder inaktiv.")
            row = con.execute("SELECT count(DISTINCT z.unternehmen_id),count(DISTINCT z.gebiet_schluessel) FROM gebietszuordnungen z JOIN unternehmen u ON u.id=z.unternehmen_id WHERE z.gewerk_id=? AND u.aktiv=1", (gewerk_id,)).fetchone()
            return ExportVorschau(g[0], row[0], row[1], dateiname_fuer_gewerk(g[0]))
    def exportieren(self, gewerk_id: int, ordner: Path) -> Path:
        info = self.vorschau(gewerk_id); ordner = Path(ordner); ordner.mkdir(parents=True, exist_ok=True)
        with self.db.connect() as con:
            rows = con.execute("""SELECT z.gebiet_schluessel,b.geometrie,u.name,u.pps_nummer FROM gebietszuordnungen z
                JOIN unternehmen u ON u.id=z.unternehmen_id JOIN gebiete b ON b.schluessel=z.gebiet_schluessel
                WHERE z.gewerk_id=? AND u.aktiv=1 ORDER BY z.gebiet_schluessel,u.name COLLATE NOCASE,u.pps_nummer""", (gewerk_id,)).fetchall()
            features = []
            for key in sorted({r[0] for r in rows}):
                group = [r for r in rows if r[0] == key]
                firmen, pps = [r[2] for r in group], [r[3] for r in group]
                features.append({"type":"Feature", "geometry":json.loads(group[0][1]), "properties":{
                    "gebiet":key,"gewerk":info.gewerk,"firmen":firmen,"pps_nummern":pps,
                    "dienstleister":[f"{n} – {p}" for n,p in zip(firmen,pps)],"anzahl_dienstleister":len(group)}})
            ziel = ordner / info.dateiname
            try:
                ziel.write_text(json.dumps({"type":"FeatureCollection","features":features}, ensure_ascii=False, indent=2), encoding="utf-8")
                result = "Erfolgreich"
            except OSError:
                result = "Fehlgeschlagen"; raise
            finally:
                con.execute("INSERT INTO export_protokoll(gewerk_id,dateiname,speicherort,ergebnis) VALUES (?,?,?,?)", (gewerk_id, info.dateiname, str(ordner), result))
            return ziel
