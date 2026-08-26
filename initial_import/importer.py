from __future__ import annotations
import argparse, csv
from dataclasses import dataclass, field
from pathlib import Path
from app.datenbank import Database
from app.modelle import UnternehmenEingabe
from app.services import Verwaltung
from app.validierung import Validierungsfehler

SPALTEN = ["Gewerk", "Unternehmen", "PPS_Nummer", "PLZ"]
# Diese zweistelligen Werte sind im deutschen Postleitzahlensystem nicht
# vergeben und haben deshalb zu Recht keine Fläche im detaillierten GeoJSON.
NICHT_VERGEBENE_PLZ2 = {"05", "11", "43", "62"}

@dataclass
class ImportBericht:
    eingelesene_zeilen: int = 0; unternehmen: int = 0; gewerke: int = 0; zuordnungen: int = 0
    duplikate: int = 0; uebersprungene_zeilen: int = 0; fehlerhafte_zeilen: int = 0
    fehler: list[str] = field(default_factory=list); hinweise: list[str] = field(default_factory=list)
    def __str__(self):
        return (f"Eingelesene Zeilen: {self.eingelesene_zeilen}\nAngelegte Unternehmen: {self.unternehmen}\n"
                f"Angelegte Gewerke: {self.gewerke}\nGespeicherte Gebietszuordnungen: {self.zuordnungen}\n"
                f"Übersprungene Duplikate: {self.duplikate}\nSonstige übersprungene Zeilen: {self.uebersprungene_zeilen}\n"
                f"Fehlerhafte Zeilen: {self.fehlerhafte_zeilen}\n" + "\n".join(self.hinweise + self.fehler))

def finde_csv(input_ordner: Path) -> Path:
    files = list(Path(input_ordner).glob("*.csv"))
    if len(files) != 1: raise ValueError(f"Im Eingabeordner muss genau eine CSV-Datei liegen; gefunden: {len(files)}.")
    if not files[0].is_file(): raise ValueError("Die CSV-Datei ist nicht lesbar.")
    return files[0]

def importiere(csv_path: Path, db_path: Path, ueberschreiben=False) -> ImportBericht:
    csv_path, db_path = Path(csv_path), Path(db_path)
    if db_path.exists() and not ueberschreiben: raise FileExistsError("Die Datenbank existiert bereits. Nutzen Sie --ueberschreiben nur bewusst in der Entwicklung.")
    raw = csv_path.read_text(encoding="utf-8-sig")
    first = raw.splitlines()[0] if raw.splitlines() else ""
    if first.count(";") != 3: raise ValueError("Die CSV-Datei muss ein Semikolon als Trennzeichen verwenden.")
    rows = list(csv.DictReader(raw.splitlines(), delimiter=";"))
    if not rows and first.split(";") != SPALTEN: pass
    headers = next(csv.reader([first], delimiter=";"), [])
    if headers != SPALTEN: raise ValueError(f"Benötigte Spalten (in dieser Reihenfolge): {', '.join(SPALTEN)}.")
    report = ImportBericht(eingelesene_zeilen=len(rows)); records={}; names={}; seen=set(); trades=set()
    uebersprungene_null_pps = 0; uebersprungene_plz: dict[str, int] = {}
    for line, row in enumerate(rows, 2):
        values = {k:(row.get(k) or "").strip() for k in SPALTEN}
        missing=[k for k,v in values.items() if not v]
        if missing:
            report.fehler.append(f"Zeile {line}: Pflichtfeld(er) leer: {', '.join(missing)}."); report.fehlerhafte_zeilen += 1; continue
        pps,name,trade,area=values["PPS_Nummer"],values["Unternehmen"],values["Gewerk"],values["PLZ"].upper()
        if pps == "0":
            # 0 ist ein Platzhalter und keine eindeutige PPS-Nummer. Solche
            # Zeilen dürfen nicht zu falschen Firmenzusammenführungen führen.
            report.uebersprungene_zeilen += 1; uebersprungene_null_pps += 1; continue
        if area in NICHT_VERGEBENE_PLZ2:
            # Nicht vergebene PLZ-2-Bereiche besitzen keine exportierbare
            # Geometrie. Andere Zeilen derselben Firma werden normal übernommen.
            report.uebersprungene_zeilen += 1
            uebersprungene_plz[area] = uebersprungene_plz.get(area, 0) + 1
            continue
        if pps in names and names[pps] != name:
            report.fehler.append(f"Zeile {line}: PPS-Nummer {pps} hat widersprüchliche Unternehmensnamen."); report.fehlerhafte_zeilen += 1; continue
        key=(pps,trade,area)
        if key in seen: report.duplikate += 1; continue
        names[pps]=name; seen.add(key); trades.add(trade); records.setdefault(pps, {}).setdefault(trade,set()).add(area)
    if uebersprungene_null_pps:
        report.hinweise.append(f"Hinweis: {uebersprungene_null_pps} Zeile(n) mit PPS-Nummer 0 wurden übersprungen.")
    if uebersprungene_plz:
        details = ", ".join(f"{plz} ({anzahl} Zeile(n))" for plz, anzahl in sorted(uebersprungene_plz.items()))
        report.hinweise.append(f"Hinweis: Nicht vergebene PLZ-2-Bereiche wurden übersprungen: {details}.")
    temp = db_path.with_suffix(db_path.suffix + ".import")
    if temp.exists(): temp.unlink()
    db=Database(temp); db.initialize(); service=Verwaltung(db)
    # Importiert werden können nur zuvor mit echten Geometrien geladene Gebiete.
    # Bei einer neuen DB übernehmen wir den Katalog aus den ausgelieferten Dateien.
    from app.datenbank.gebiete import ausgelieferte_gebietsdateien, lade_gebiete
    lade_gebiete(db, ausgelieferte_gebietsdateien())
    for pps, mapping in records.items():
        try: service.speichere_unternehmen(UnternehmenEingabe(names[pps],pps,True,mapping)); report.unternehmen += 1; report.zuordnungen += sum(map(len,mapping.values()))
        except Validierungsfehler as exc: report.fehler.append(f"PPS {pps}: {exc}"); report.fehlerhafte_zeilen += sum(map(len,mapping.values()))
    report.gewerke=len(trades)
    if report.fehler: temp.unlink(missing_ok=True); return report
    if db_path.exists(): db_path.unlink()
    temp.replace(db_path); return report

def main():
    p=argparse.ArgumentParser(description="Einmaliger CSV-Import für Dienstleisterkarten")
    p.add_argument("--input", type=Path, default=Path(__file__).parent/"input"); p.add_argument("--datenbank", type=Path, required=True); p.add_argument("--ueberschreiben", action="store_true")
    a=p.parse_args(); print(importiere(finde_csv(a.input),a.datenbank,a.ueberschreiben))
if __name__ == "__main__": main()
