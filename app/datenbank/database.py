from __future__ import annotations
from contextlib import contextmanager
import sqlite3
from collections.abc import Iterator
from pathlib import Path

SCHEMA_VERSION = 2

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS unternehmen (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL CHECK(trim(name) <> ''),
 pps_nummer TEXT NOT NULL CHECK(trim(pps_nummer) <> ''), aktiv INTEGER NOT NULL DEFAULT 1 CHECK(aktiv IN (0,1)),
 erstellt_am TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, geaendert_am TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS gewerke (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE CHECK(trim(name) <> ''), aktiv INTEGER NOT NULL DEFAULT 1 CHECK(aktiv IN (0,1))
);
CREATE TABLE IF NOT EXISTS gebiete (
 schluessel TEXT PRIMARY KEY, anzeigename TEXT NOT NULL, typ TEXT NOT NULL CHECK(typ IN ('PLZ2','LAND','REGION')),
 geometrie TEXT NOT NULL, label_lon REAL, label_lat REAL
);
CREATE TABLE IF NOT EXISTS unternehmen_gewerke (
 unternehmen_id INTEGER NOT NULL REFERENCES unternehmen(id) ON DELETE CASCADE,
 gewerk_id INTEGER NOT NULL REFERENCES gewerke(id) ON DELETE RESTRICT,
 PRIMARY KEY(unternehmen_id, gewerk_id)
);
CREATE TABLE IF NOT EXISTS gebietszuordnungen (
 unternehmen_id INTEGER NOT NULL, gewerk_id INTEGER NOT NULL, gebiet_schluessel TEXT NOT NULL REFERENCES gebiete(schluessel) ON DELETE RESTRICT,
 PRIMARY KEY(unternehmen_id, gewerk_id, gebiet_schluessel),
 FOREIGN KEY(unternehmen_id, gewerk_id) REFERENCES unternehmen_gewerke(unternehmen_id, gewerk_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS export_protokoll (
 id INTEGER PRIMARY KEY, gewerk_id INTEGER NOT NULL REFERENCES gewerke(id) ON DELETE RESTRICT,
 zeitpunkt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, dateiname TEXT NOT NULL, speicherort TEXT NOT NULL, ergebnis TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_unternehmen_name ON unternehmen(name);
CREATE UNIQUE INDEX IF NOT EXISTS ux_unternehmen_pps_nummer
 ON unternehmen(pps_nummer) WHERE pps_nummer <> '0';
CREATE INDEX IF NOT EXISTS idx_zuordnung_gewerk ON gebietszuordnungen(gewerk_id, gebiet_schluessel);
"""

MIGRATION_1_NACH_2 = """
PRAGMA foreign_keys=OFF;
BEGIN;
CREATE TABLE unternehmen_neu (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL CHECK(trim(name) <> ''),
 pps_nummer TEXT NOT NULL CHECK(trim(pps_nummer) <> ''), aktiv INTEGER NOT NULL DEFAULT 1 CHECK(aktiv IN (0,1)),
 erstellt_am TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, geaendert_am TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO unternehmen_neu SELECT * FROM unternehmen;
DROP TABLE unternehmen;
ALTER TABLE unternehmen_neu RENAME TO unternehmen;
UPDATE schema_version SET version=2;
COMMIT;
PRAGMA foreign_keys=ON;
"""


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Öffnet eine transaktionale Verbindung und schließt sie garantiert.

        Der Kontextmanager von ``sqlite3.Connection`` schreibt beziehungsweise
        verwirft lediglich die Transaktion; er schließt die Verbindung nicht.
        Das explizite ``close`` ist insbesondere unter Windows nötig, bevor eine
        Datenbankdatei gelöscht oder umbenannt werden kann.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        try:
            with con:
                yield con
        finally:
            con.close()

    def initialize(self) -> None:
        with self.connect() as con:
            con.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
            row = con.execute("SELECT version FROM schema_version").fetchone()
            if row is None:
                con.executescript(SCHEMA)
                con.execute("INSERT INTO schema_version VALUES (?)", (SCHEMA_VERSION,))
            elif row[0] == 1:
                con.executescript(MIGRATION_1_NACH_2)
                con.executescript(SCHEMA)
            elif row[0] == SCHEMA_VERSION:
                con.executescript(SCHEMA)
            else:
                raise RuntimeError(f"Nicht unterstützte Datenbankversion {row[0]}.")

    def transaction(self):
        return self.connect()
