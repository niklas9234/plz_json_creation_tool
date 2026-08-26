from __future__ import annotations
import argparse, csv, sqlite3
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
    veroeffentlicht: bool = False
    def __str__(self):
        status = "ERFOLGREICH" if self.veroeffentlicht else "NICHT IMPORTIERT"
        return (f"Importstatus: {status}\nEingelesene Zeilen: {self.eingelesene_zeilen}\nAngelegte Unternehmen: {self.unternehmen}\n"
                f"Angelegte Gewerke: {self.gewerke}\nGespeicherte Gebietszuordnungen: {self.zuordnungen}\n"
                f"Übersprungene Duplikate: {self.duplikate}\nSonstige übersprungene Zeilen: {self.uebersprungene_zeilen}\n"
                f"Fehlerhafte Zeilen: {self.fehlerhafte_zeilen}\n" + "\n".join(self.hinweise + self.fehler))

def finde_csv(input_ordner: Path) -> Path:
    files = list(Path(input_ordner).glob("*.csv"))
    if len(files) != 1: raise ValueError(f"Im Eingabeordner muss genau eine CSV-Datei liegen; gefunden: {len(files)}.")
    if not files[0].is_file(): raise ValueError("Die CSV-Datei ist nicht lesbar.")
    return files[0]

def hat_fachdaten(db_path: Path) -> bool:
    """Prüft, ob eine vorhandene DB bereits zu erhaltende Nutzdaten enthält."""
    try:
        with sqlite3.connect(db_path) as con:
            tabellen = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for tabelle in ("unternehmen", "gewerke", "gebietszuordnungen", "export_protokoll"):
                if tabelle in tabellen and con.execute(f"SELECT 1 FROM {tabelle} LIMIT 1").fetchone():
                    return True
            return False
    except sqlite3.DatabaseError as exc:
        raise ValueError(f"Die vorhandene Zieldatei ist keine lesbare Dienstleister-Datenbank: {db_path}") from exc

def importiere(csv_path: Path, db_path: Path, ueberschreiben=False) -> ImportBericht:
    csv_path, db_path = Path(csv_path), Path(db_path)
    if db_path.exists() and not ueberschreiben and hat_fachdaten(db_path):
        raise FileExistsError("Die Datenbank enthält bereits Unternehmen oder Gewerke. Nutzen Sie --ueberschreiben nur für einen bewusst vollständigen Neuimport.")
    raw = csv_path.read_text(encoding="utf-8-sig")
    first = raw.splitlines()[0] if raw.splitlines() else ""
    if first.count(";") != 3: raise ValueError("Die CSV-Datei muss ein Semikolon als Trennzeichen verwenden.")
    rows = list(csv.DictReader(raw.splitlines(), delimiter=";"))
    if not rows and first.split(";") != SPALTEN: pass
    headers = next(csv.reader([first], delimiter=";"), [])
    if headers != SPALTEN: raise ValueError(f"Benötigte Spalten (in dieser Reihenfolge): {', '.join(SPALTEN)}.")
    report = ImportBericht(eingelesene_zeilen=len(rows)); records={}; names={}; namen_je_pps={}; pps_werte={}; seen=set(); trades=set()
    uebersprungene_plz: dict[str, int] = {}
    for line, row in enumerate(rows, 2):
        values = {k:(row.get(k) or "").strip() for k in SPALTEN}
        missing=[k for k,v in values.items() if not v]
        if missing:
            report.fehler.append(f"Zeile {line}: Pflichtfeld(er) leer: {', '.join(missing)}."); report.fehlerhafte_zeilen += 1; continue
        pps,name,trade,area=values["PPS_Nummer"],values["Unternehmen"],values["Gewerk"],values["PLZ"].upper()
        if area in NICHT_VERGEBENE_PLZ2:
            # Nicht vergebene PLZ-2-Bereiche besitzen keine exportierbare
            # Geometrie. Andere Zeilen derselben Firma werden normal übernommen.
            report.uebersprungene_zeilen += 1
            uebersprungene_plz[area] = uebersprungene_plz.get(area, 0) + 1
            continue
        if pps != "0" and pps in namen_je_pps and namen_je_pps[pps] != name:
            report.fehler.append(f"Zeile {line}: PPS-Nummer {pps} hat widersprüchliche Unternehmensnamen."); report.fehlerhafte_zeilen += 1; continue
        # Eine echte PPS-Nummer identifiziert die Firma. Der Platzhalter 0 ist
        # dagegen nicht eindeutig; hier bildet zusätzlich der Firmenname die
        # Identität, damit alle Zeilen dieser Firma erhalten bleiben.
        identity = (pps, name.casefold()) if pps == "0" else (pps, "")
        key=(identity,trade,area)
        if key in seen: report.duplikate += 1; continue
        names[identity]=name; namen_je_pps[pps]=name; pps_werte[identity]=pps; seen.add(key); trades.add(trade); records.setdefault(identity, {}).setdefault(trade,set()).add(area)
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
    if report.fehler:
        report.unternehmen = report.gewerke = report.zuordnungen = 0
        temp.unlink(missing_ok=True); return report
    if db_path.exists(): db_path.unlink()
    temp.replace(db_path); report.veroeffentlicht = True; return report

def main():
    p=argparse.ArgumentParser(description="Einmaliger CSV-Import für Dienstleisterkarten")
    p.add_argument("--input", type=Path, default=Path(__file__).parent/"input"); p.add_argument("--datenbank", type=Path, required=True); p.add_argument("--ueberschreiben", action="store_true")
    a=p.parse_args(); csv_path=finde_csv(a.input)
    print(f"CSV-Datei: {csv_path.resolve()}")
    print(f"Zieldatenbank: {a.datenbank.resolve()}")
    report=importiere(csv_path,a.datenbank,a.ueberschreiben); print(report)
    return 0 if report.veroeffentlicht else 1
if __name__ == "__main__": raise SystemExit(main())
