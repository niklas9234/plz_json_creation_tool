from datetime import datetime
from pathlib import Path
import shutil
from app.datenbank import Database


class BackupService:
    def __init__(self, db: Database, ordner: Path): self.db, self.ordner = db, Path(ordner)
    def erstellen(self, zeitpunkt: datetime | None = None) -> Path:
        self.ordner.mkdir(parents=True, exist_ok=True)
        basis = f"dienstleister_{(zeitpunkt or datetime.now()):%Y-%m-%d_%H%M%S}"
        ziel = self.ordner / f"{basis}.db"
        nummer = 1
        while ziel.exists():
            ziel = self.ordner / f"{basis}_{nummer}.db"
            nummer += 1
        with self.db.connect() as quelle, __import__('sqlite3').connect(ziel) as dest: quelle.backup(dest)
        return ziel
    def wiederherstellen(self, quelle: Path) -> Path:
        quelle = Path(quelle)
        if not quelle.is_file(): raise ValueError("Die ausgewählte Sicherungsdatei wurde nicht gefunden.")
        vorsicherung = self.erstellen()
        shutil.copy2(quelle, self.db.path)
        try: self.db.initialize()
        except Exception:
            shutil.copy2(vorsicherung, self.db.path)
            raise ValueError("Die Sicherung ist keine kompatible Dienstleister-Datenbank.")
        return vorsicherung
