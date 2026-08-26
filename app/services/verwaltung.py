from __future__ import annotations
import sqlite3
from app.datenbank import Database
from app.modelle import UnternehmenEingabe
from app.validierung import Validierungsfehler, validiere_unternehmen


class Verwaltung:
    def __init__(self, db: Database): self.db = db

    def gebietsschluessel(self) -> set[str]:
        with self.db.connect() as con:
            return {r[0] for r in con.execute("SELECT schluessel FROM gebiete")}

    def speichere_unternehmen(self, eingabe: UnternehmenEingabe, unternehmen_id: int | None = None) -> int:
        cleaned = UnternehmenEingabe(eingabe.name.strip(), eingabe.pps_nummer.strip(), eingabe.aktiv,
            {g.strip(): {x.strip().upper() for x in v} for g, v in eingabe.gebiete_je_gewerk.items()})
        validiere_unternehmen(cleaned, self.gebietsschluessel())
        try:
            with self.db.connect() as con:
                if unternehmen_id is None:
                    cur = con.execute("INSERT INTO unternehmen(name,pps_nummer,aktiv) VALUES (?,?,?)", (cleaned.name, cleaned.pps_nummer, cleaned.aktiv))
                    unternehmen_id = cur.lastrowid
                else:
                    con.execute("UPDATE unternehmen SET name=?,pps_nummer=?,aktiv=?,geaendert_am=CURRENT_TIMESTAMP WHERE id=?",
                                (cleaned.name, cleaned.pps_nummer, cleaned.aktiv, unternehmen_id))
                    if con.total_changes == 0: raise Validierungsfehler("Das Unternehmen wurde nicht gefunden.")
                    con.execute("DELETE FROM unternehmen_gewerke WHERE unternehmen_id=?", (unternehmen_id,))
                for name, gebiete in cleaned.gebiete_je_gewerk.items():
                    con.execute("INSERT INTO gewerke(name) VALUES (?) ON CONFLICT(name) DO NOTHING", (name,))
                    gid = con.execute("SELECT id FROM gewerke WHERE name=? COLLATE NOCASE", (name,)).fetchone()[0]
                    con.execute("INSERT INTO unternehmen_gewerke VALUES (?,?)", (unternehmen_id, gid))
                    con.executemany("INSERT INTO gebietszuordnungen VALUES (?,?,?)", ((unternehmen_id, gid, x) for x in sorted(gebiete)))
                return int(unternehmen_id)
        except sqlite3.IntegrityError as exc:
            if "pps_nummer" in str(exc): raise Validierungsfehler("Diese PPS-Nummer ist bereits vergeben.") from exc
            raise Validierungsfehler("Die Angaben konnten wegen einer doppelten oder ungültigen Zuordnung nicht gespeichert werden.") from exc

    def suche(self, text="", gewerk=None, aktiv: bool | None=None):
        sql = "SELECT DISTINCT u.* FROM unternehmen u LEFT JOIN unternehmen_gewerke ug ON ug.unternehmen_id=u.id LEFT JOIN gewerke g ON g.id=ug.gewerk_id WHERE (u.name LIKE ? OR u.pps_nummer LIKE ?)"
        params: list[object] = [f"%{text.strip()}%"] * 2
        if gewerk: sql += " AND g.name=?"; params.append(gewerk)
        if aktiv is not None: sql += " AND u.aktiv=?"; params.append(aktiv)
        sql += " ORDER BY u.name COLLATE NOCASE, u.pps_nummer"
        with self.db.connect() as con: return con.execute(sql, params).fetchall()

    def loesche_unternehmen(self, uid: int):
        with self.db.connect() as con: con.execute("DELETE FROM unternehmen WHERE id=?", (uid,))

    def loesche_gewerk(self, gid: int):
        try:
            with self.db.connect() as con: con.execute("DELETE FROM gewerke WHERE id=?", (gid,))
        except sqlite3.IntegrityError as exc:
            raise Validierungsfehler("Das Gewerk ist noch Unternehmen zugeordnet und kann nicht gelöscht werden.") from exc
