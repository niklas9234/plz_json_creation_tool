import sys
from app.config import ensure_directories
from app.datenbank import Database
from app.datenbank.gebiete import ausgelieferte_gebietsdateien, lade_gebiete


def main():
    try:
        from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QLabel
        from app.ui.bestandslisten import UnternehmenListe
    except ImportError:
        print("PySide6 fehlt. Installieren Sie die Abhängigkeiten mit: pip install .", file=sys.stderr); return 1
    paths=ensure_directories(); db=Database(paths['daten']/ 'dienstleister.db'); db.initialize()
    if not __import__('sqlite3').connect(db.path).execute('SELECT 1 FROM gebiete LIMIT 1').fetchone():
        lade_gebiete(db, ausgelieferte_gebietsdateien())
    app=QApplication(sys.argv); app.setApplicationName('Dienstleisterkarten')
    window=QMainWindow(); window.setWindowTitle('Dienstleisterkarten'); window.resize(1000,700)
    tabs=QTabWidget()
    pages={'Unternehmen':UnternehmenListe(db)}
    texts={
      'Informationen':'Dienstleisterkarten – Inhalte lokal anzeigen und bearbeiten.'}
    for title,page in pages.items():
        tabs.addTab(page,title)
    for title,text in texts.items():
        page=QWidget(); layout=QVBoxLayout(page); layout.addWidget(QLabel(text)); layout.addStretch(); tabs.addTab(page,title)
    window.setCentralWidget(tabs); window.show(); return app.exec()
if __name__=='__main__': raise SystemExit(main())
