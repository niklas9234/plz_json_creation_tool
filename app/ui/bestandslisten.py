from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.datenbank import Database


def _item(text: object, sort_value: object | None = None) -> QTableWidgetItem:
    item = QTableWidgetItem(str(text))
    if sort_value is not None:
        item.setData(Qt.ItemDataRole.UserRole, sort_value)
    return item


class Bestandsliste(QWidget):
    """Gemeinsame, nicht editierbare Tabellenansicht für den Datenbestand."""

    def __init__(self, db: Database, headers: list[str], parent: QWidget | None = None):
        super().__init__(parent)
        self.db = db
        self.suche = QLineEdit()
        self.suche.setClearButtonEnabled(True)
        self.suche.setPlaceholderText("Suchen …")
        self.anzahl = QLabel()
        refresh = QPushButton("Aktualisieren")
        refresh.clicked.connect(self.laden)

        controls = QHBoxLayout()
        controls.addWidget(self.suche, 1)
        controls.addWidget(refresh)
        controls.addWidget(self.anzahl)

        self.tabelle = QTableWidget(0, len(headers))
        self.tabelle.setHorizontalHeaderLabels(headers)
        self.tabelle.setAlternatingRowColors(True)
        self.tabelle.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabelle.setSortingEnabled(True)
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.horizontalHeader().setStretchLastSection(True)

        layout = QVBoxLayout(self)
        layout.addLayout(controls)
        layout.addWidget(self.tabelle, 1)
        self.suche.textChanged.connect(self.laden)

    def _fuellen(self, rows: list[tuple[object, ...]]) -> None:
        self.tabelle.setSortingEnabled(False)
        self.tabelle.setRowCount(len(rows))
        for row_index, values in enumerate(rows):
            for column_index, value in enumerate(values):
                self.tabelle.setItem(row_index, column_index, _item(value))
        self.tabelle.setSortingEnabled(True)
        self.tabelle.resizeColumnsToContents()
        self.anzahl.setText(f"{len(rows)} Einträge")


class UnternehmenListe(Bestandsliste):
    def __init__(self, db: Database, parent: QWidget | None = None):
        super().__init__(db, ["Unternehmen", "PPS-Nummer", "Aktiv", "Gewerke", "Gebiete"], parent)
        self.nur_aktive = QCheckBox("Nur aktive")
        self.nur_aktive.stateChanged.connect(self.laden)
        self.layout().itemAt(0).layout().insertWidget(1, self.nur_aktive)
        self.suche.setPlaceholderText("Unternehmen oder PPS-Nummer suchen …")
        self.laden()

    def laden(self) -> None:
        text = f"%{self.suche.text().strip()}%"
        aktiv_filter = "AND u.aktiv=1" if self.nur_aktive.isChecked() else ""
        with self.db.connect() as con:
            rows = con.execute(
                f"""SELECT u.name, u.pps_nummer,
                       CASE u.aktiv WHEN 1 THEN 'Ja' ELSE 'Nein' END,
                       group_concat(DISTINCT g.name), count(DISTINCT z.gebiet_schluessel)
                    FROM unternehmen u
                    LEFT JOIN unternehmen_gewerke ug ON ug.unternehmen_id=u.id
                    LEFT JOIN gewerke g ON g.id=ug.gewerk_id
                    LEFT JOIN gebietszuordnungen z ON z.unternehmen_id=u.id
                    WHERE (u.name LIKE ? OR u.pps_nummer LIKE ?) {aktiv_filter}
                    GROUP BY u.id
                    ORDER BY u.name COLLATE NOCASE, u.pps_nummer""",
                (text, text),
            ).fetchall()
        self._fuellen([(row[0], row[1], row[2], row[3] or "–", row[4]) for row in rows])


class GewerkeListe(Bestandsliste):
    def __init__(self, db: Database, parent: QWidget | None = None):
        super().__init__(db, ["Gewerk", "Aktiv", "Unternehmen", "Gebiete"], parent)
        self.suche.setPlaceholderText("Gewerk suchen …")
        self.laden()

    def laden(self) -> None:
        text = f"%{self.suche.text().strip()}%"
        with self.db.connect() as con:
            rows = con.execute(
                """SELECT g.name, CASE g.aktiv WHEN 1 THEN 'Ja' ELSE 'Nein' END,
                          count(DISTINCT ug.unternehmen_id), count(DISTINCT z.gebiet_schluessel)
                   FROM gewerke g
                   LEFT JOIN unternehmen_gewerke ug ON ug.gewerk_id=g.id
                   LEFT JOIN gebietszuordnungen z ON z.gewerk_id=g.id
                   WHERE g.name LIKE ?
                   GROUP BY g.id ORDER BY g.name COLLATE NOCASE""",
                (text,),
            ).fetchall()
        self._fuellen([tuple(row) for row in rows])
