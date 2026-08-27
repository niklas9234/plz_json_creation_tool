from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.datenbank import Database
from app.modelle import UnternehmenEingabe
from app.services import Verwaltung
from app.validierung import Validierungsfehler
from app.ui.gebietskarte import Gebietskarte


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

    def _fuellen(self, rows: list[tuple[object, ...]], row_ids: list[int] | None = None) -> None:
        self.tabelle.setSortingEnabled(False)
        self.tabelle.setRowCount(len(rows))
        for row_index, values in enumerate(rows):
            for column_index, value in enumerate(values):
                item = _item(value)
                if column_index == 0 and row_ids is not None:
                    item.setData(Qt.ItemDataRole.UserRole, row_ids[row_index])
                self.tabelle.setItem(row_index, column_index, item)
        self.tabelle.setSortingEnabled(True)
        self.tabelle.resizeColumnsToContents()
        self.anzahl.setText(f"{len(rows)} Einträge")


class UnternehmenListe(Bestandsliste):
    def __init__(self, db: Database, parent: QWidget | None = None):
        super().__init__(db, ["Unternehmen", "PPS-Nummer", "Aktiv", "Gewerke", "Gebiete"], parent)
        self.nur_aktive = QCheckBox("Nur aktive")
        self.nur_aktive.stateChanged.connect(self.laden)
        self.layout().itemAt(0).layout().insertWidget(1, self.nur_aktive)
        neu = QPushButton("Neu")
        bearbeiten = QPushButton("Bearbeiten")
        neu.clicked.connect(self.neu)
        bearbeiten.clicked.connect(self.bearbeiten)
        self.layout().itemAt(0).layout().insertWidget(2, neu)
        self.layout().itemAt(0).layout().insertWidget(3, bearbeiten)
        self.tabelle.doubleClicked.connect(self.bearbeiten)
        self.tabelle.itemSelectionChanged.connect(self._auswahl_laden)
        self.suche.setPlaceholderText("Unternehmen oder PPS-Nummer suchen …")
        self._detail_aufbauen()
        self.laden()

    def _detail_aufbauen(self) -> None:
        root = self.layout()
        controls = root.takeAt(0).layout()
        root.takeAt(0)
        liste = QWidget()
        listen_layout = QVBoxLayout(liste)
        listen_layout.setContentsMargins(0, 0, 0, 0)
        listen_layout.addLayout(controls)
        listen_layout.addWidget(self.tabelle, 1)

        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        self.detail_name = QLabel("Kein Unternehmen ausgewählt")
        self.detail_name.setStyleSheet("font-size: 18px; font-weight: bold")
        self.detail_pps = QLabel("PPS-Nummer: –")
        self.detail_aktiv = QLabel("Status: –")
        self.detail_gewerke = QLabel("Gewerke: –")
        self.karte = Gebietskarte(nur_lesen=True)
        self.karte.setMinimumHeight(280)
        self.legende = QWidget()
        self.legenden_layout = QVBoxLayout(self.legende)
        self.legenden_layout.setContentsMargins(0, 0, 0, 0)
        legenden_scroll = QScrollArea()
        legenden_scroll.setWidgetResizable(True)
        legenden_scroll.setWidget(self.legende)
        legenden_scroll.setMaximumHeight(130)
        self.detail_bearbeiten = QPushButton("Unternehmen bearbeiten")
        self.detail_bearbeiten.setEnabled(False)
        self.detail_bearbeiten.clicked.connect(self.bearbeiten)
        for widget in (self.detail_name, self.detail_pps, self.detail_aktiv, self.detail_gewerke, self.karte, legenden_scroll, self.detail_bearbeiten):
            detail_layout.addWidget(widget)
        detail_layout.setStretch(4, 1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(liste)
        splitter.addWidget(detail)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter)
        self.splitter = splitter

    def _auswahl_laden(self) -> None:
        row = self.tabelle.currentRow()
        item = self.tabelle.item(row, 0) if row >= 0 else None
        if item is None:
            self._detail_leeren()
            return
        unternehmen_id = int(item.data(Qt.ItemDataRole.UserRole))
        with self.db.connect() as con:
            unternehmen = con.execute(
                "SELECT name, pps_nummer, aktiv FROM unternehmen WHERE id=?", (unternehmen_id,)
            ).fetchone()
            rows = con.execute(
                """SELECT g.name, z.gebiet_schluessel, b.geometrie
                   FROM unternehmen_gewerke ug JOIN gewerke g ON g.id=ug.gewerk_id
                   LEFT JOIN gebietszuordnungen z ON z.unternehmen_id=ug.unternehmen_id AND z.gewerk_id=ug.gewerk_id
                   LEFT JOIN gebiete b ON b.schluessel=z.gebiet_schluessel
                   WHERE ug.unternehmen_id=? ORDER BY g.name COLLATE NOCASE, z.gebiet_schluessel""",
                (unternehmen_id,),
            ).fetchall()
        if unternehmen is None:
            self._detail_leeren()
            return
        zuordnungen: dict[str, set[str]] = {}
        geometrien: dict[str, object] = {}
        for gewerk, schluessel, geometrie in rows:
            zuordnungen.setdefault(gewerk, set())
            if schluessel is not None:
                zuordnungen[gewerk].add(schluessel)
                geometrien[schluessel] = geometrie
        self.detail_name.setText(unternehmen[0])
        self.detail_pps.setText(f"PPS-Nummer: {unternehmen[1]}")
        self.detail_aktiv.setText(f"Status: {'Aktiv' if unternehmen[2] else 'Inaktiv'}")
        self.detail_gewerke.setText("Gewerke: " + (", ".join(zuordnungen) or "–"))
        self.detail_bearbeiten.setEnabled(True)
        self.karte.set_zuordnungen(zuordnungen, geometrien)
        self._legende_fuellen(zuordnungen)

    def _legende_fuellen(self, zuordnungen: dict[str, set[str]]) -> None:
        while self.legenden_layout.count():
            child = self.legenden_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        for gewerk, gebiete in zuordnungen.items():
            checkbox = QCheckBox(f"{gewerk} ({len(gebiete)} Gebiete)")
            checkbox.setChecked(True)
            checkbox.toggled.connect(lambda sichtbar, name=gewerk: self.karte.set_gewerk_sichtbar(name, sichtbar))
            self.legenden_layout.addWidget(checkbox)

    def _detail_leeren(self) -> None:
        self.detail_name.setText("Kein Unternehmen ausgewählt")
        self.detail_pps.setText("PPS-Nummer: –")
        self.detail_aktiv.setText("Status: –")
        self.detail_gewerke.setText("Gewerke: –")
        self.detail_bearbeiten.setEnabled(False)
        self.karte.set_zuordnungen({}, {})
        self._legende_fuellen({})

    def laden(self) -> None:
        text = f"%{self.suche.text().strip()}%"
        aktiv_filter = "AND u.aktiv=1" if self.nur_aktive.isChecked() else ""
        with self.db.connect() as con:
            rows = con.execute(
                f"""SELECT u.id, u.name, u.pps_nummer,
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
        self._fuellen(
            [(row[1], row[2], row[3], row[4] or "–", row[5]) for row in rows],
            [row[0] for row in rows],
        )
        self._auswahl_laden()

    def neu(self) -> None:
        self._dialog_oeffnen(None)

    def bearbeiten(self, *_args: object) -> None:
        row = self.tabelle.currentRow()
        if row < 0:
            QMessageBox.information(self, "Unternehmen bearbeiten", "Bitte wählen Sie zuerst ein Unternehmen aus.")
            return
        self._dialog_oeffnen(int(self.tabelle.item(row, 0).data(Qt.ItemDataRole.UserRole)))

    def _dialog_oeffnen(self, unternehmen_id: int | None) -> None:
        dialog = UnternehmenDialog(self.db, unternehmen_id, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.laden()


class UnternehmenDialog(QDialog):
    """Editor, der Änderungen erst nach einer ausdrücklichen Bestätigung speichert."""

    def __init__(self, db: Database, unternehmen_id: int | None, parent: QWidget | None = None):
        super().__init__(parent)
        self.db = db
        self.unternehmen_id = unternehmen_id
        self.setWindowTitle("Unternehmen bearbeiten" if unternehmen_id is not None else "Unternehmen anlegen")
        self.setMinimumWidth(520)
        self.name = QLineEdit()
        self.pps_nummer = QLineEdit()
        self.aktiv = QCheckBox("Aktiv")
        self.aktiv.setChecked(True)
        self.zuordnungen = QPlainTextEdit()
        self.zuordnungen.setPlaceholderText("Zum Beispiel:\nGerüstbau: 04, 06, LUX\nKran: 10")
        self.karte = Gebietskarte(nur_lesen=False)
        self.karte.setMinimumHeight(220)

        form = QFormLayout()
        form.addRow("Unternehmen:", self.name)
        form.addRow("PPS-Nummer:", self.pps_nummer)
        form.addRow("Status:", self.aktiv)
        form.addRow("Gewerke und Gebiete:", self.zuordnungen)
        hinweis = QLabel("Eine Zeile je Gewerk; Gebiete nach dem Doppelpunkt durch Kommas trennen.")
        hinweis.setWordWrap(True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Speichern")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Abbrechen")
        buttons.accepted.connect(self.speichern)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(hinweis)
        layout.addWidget(self.karte)
        layout.addWidget(buttons)
        if unternehmen_id is not None:
            self._laden()

    def _laden(self) -> None:
        with self.db.connect() as con:
            row = con.execute("SELECT name, pps_nummer, aktiv FROM unternehmen WHERE id=?", (self.unternehmen_id,)).fetchone()
            zuordnungen = con.execute(
                """SELECT g.name, group_concat(z.gebiet_schluessel, ', ')
                   FROM unternehmen_gewerke ug JOIN gewerke g ON g.id=ug.gewerk_id
                   LEFT JOIN gebietszuordnungen z ON z.unternehmen_id=ug.unternehmen_id AND z.gewerk_id=ug.gewerk_id
                   WHERE ug.unternehmen_id=? GROUP BY g.id ORDER BY g.name COLLATE NOCASE""",
                (self.unternehmen_id,),
            ).fetchall()
        if row is None:
            QMessageBox.warning(self, "Nicht gefunden", "Das Unternehmen wurde nicht gefunden.")
            return
        self.name.setText(row[0])
        self.pps_nummer.setText(row[1])
        self.aktiv.setChecked(bool(row[2]))
        self.zuordnungen.setPlainText("\n".join(f"{r[0]}: {r[1] or ''}" for r in zuordnungen))
        gebiete = {r[0]: {x.strip() for x in (r[1] or "").split(",") if x.strip()} for r in zuordnungen}
        schluessel = {x for werte in gebiete.values() for x in werte}
        with self.db.connect() as con:
            geometrien = {r[0]: r[1] for r in con.execute(
                f"SELECT schluessel, geometrie FROM gebiete WHERE schluessel IN ({','.join('?' for _ in schluessel)})", tuple(schluessel)
            ).fetchall()} if schluessel else {}
        self.karte.set_zuordnungen(gebiete, geometrien)

    def _eingabe(self) -> UnternehmenEingabe:
        gebiete_je_gewerk: dict[str, set[str]] = {}
        for nummer, zeile in enumerate(self.zuordnungen.toPlainText().splitlines(), 1):
            if not zeile.strip():
                continue
            if ":" not in zeile:
                raise Validierungsfehler(f"In Zeile {nummer} fehlt der Doppelpunkt zwischen Gewerk und Gebieten.")
            gewerk, gebiete = zeile.split(":", 1)
            gebiete_je_gewerk[gewerk.strip()] = {gebiet.strip() for gebiet in gebiete.split(",") if gebiet.strip()}
        return UnternehmenEingabe(self.name.text(), self.pps_nummer.text(), self.aktiv.isChecked(), gebiete_je_gewerk)

    def speichern(self) -> None:
        try:
            eingabe = self._eingabe()
        except Validierungsfehler as exc:
            QMessageBox.warning(self, "Angaben prüfen", str(exc))
            return
        antwort = QMessageBox.question(
            self,
            "Änderungen bestätigen",
            "Sind die eingegebenen Inhalte so richtig und sollen sie gespeichert werden?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if antwort != QMessageBox.StandardButton.Yes:
            return
        try:
            Verwaltung(self.db).speichere_unternehmen(eingabe, self.unternehmen_id)
        except Validierungsfehler as exc:
            QMessageBox.warning(self, "Speichern nicht möglich", str(exc))
            return
        self.accept()


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
