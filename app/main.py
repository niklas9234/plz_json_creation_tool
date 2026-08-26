import sys
from app.config import ensure_directories
from app.datenbank import Database
from app.datenbank.gebiete import lade_gebiete


def main():
    try:
        from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QLabel
    except ImportError:
        print("PySide6 fehlt. Installieren Sie die Abhängigkeiten mit: pip install .", file=sys.stderr); return 1
    paths=ensure_directories(); db=Database(paths['daten']/ 'dienstleister.db'); db.initialize()
    if not __import__('sqlite3').connect(db.path).execute('SELECT 1 FROM gebiete LIMIT 1').fetchone():
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]; lade_gebiete(db,[root/'gebiete/deutschland_plz2.geojson',root/'gebiete/luxemburg.geojson'])
    app=QApplication(sys.argv); app.setApplicationName('Dienstleisterkarten')
    window=QMainWindow(); window.setWindowTitle('Dienstleisterkarten'); window.resize(1000,700)
    tabs=QTabWidget()
    texts={
      'Unternehmen':'Unternehmen suchen, anlegen, bearbeiten, deaktivieren oder löschen.',
      'Gewerke':'Gewerke anlegen, umbenennen, aktivieren oder deaktivieren.',
      'Export':'Wählen Sie genau ein Gewerk für den GeoJSON-Export.',
      'Sicherung und Wiederherstellung':'Datenbank manuell sichern oder nach Bestätigung wiederherstellen.',
      'Informationen':'Dienstleisterkarten – vollständig offline.'}
    for title,text in texts.items():
        page=QWidget(); layout=QVBoxLayout(page); layout.addWidget(QLabel(text)); layout.addStretch(); tabs.addTab(page,title)
    window.setCentralWidget(tabs); window.show(); return app.exec()
if __name__=='__main__': raise SystemExit(main())
