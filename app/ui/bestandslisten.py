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
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.datenbank import Database
from app.modelle import UnternehmenEingabe
from app.services import Verwaltung
from app.validierung import Validierungsfehler, validiere_unternehmen


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
        self.suche.setPlaceholderText("Unternehmen oder PPS-Nummer suchen …")
        self.laden()

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
        self.ausgangseingabe: UnternehmenEingabe | None = None
        self.setWindowTitle("Unternehmen bearbeiten" if unternehmen_id is not None else "Unternehmen anlegen")
        self.setMinimumWidth(520)
        self.name = QLineEdit()
        self.pps_nummer = QLineEdit()
        self.aktiv = QCheckBox("Aktiv")
        self.aktiv.setChecked(True)
        self.zuordnungen = QPlainTextEdit()
        self.zuordnungen.setPlaceholderText("Zum Beispiel:\nGerüstbau: 04, 06, LUX\nKran: 10")

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
        self.ausgangseingabe = self._kopiere_eingabe(self._eingabe())

    @staticmethod
    def _kopiere_eingabe(eingabe: UnternehmenEingabe) -> UnternehmenEingabe:
        """Erstellt trotz der veränderlichen Mengen eine unabhängige Momentaufnahme."""
        return UnternehmenEingabe(
            eingabe.name,
            eingabe.pps_nummer,
            eingabe.aktiv,
            {gewerk: set(gebiete) for gewerk, gebiete in eingabe.gebiete_je_gewerk.items()},
        )

    def _eingabe(self) -> UnternehmenEingabe:
        gebiete_je_gewerk: dict[str, set[str]] = {}
        for nummer, zeile in enumerate(self.zuordnungen.toPlainText().splitlines(), 1):
            if not zeile.strip():
                continue
            if ":" not in zeile:
                raise Validierungsfehler(f"In Zeile {nummer} fehlt der Doppelpunkt zwischen Gewerk und Gebieten.")
            gewerk, gebiete = zeile.split(":", 1)
            gebiete_je_gewerk[gewerk.strip()] = {
                gebiet.strip().upper() for gebiet in gebiete.split(",") if gebiet.strip()
            }
        return UnternehmenEingabe(
            self.name.text().strip(),
            self.pps_nummer.text().strip(),
            self.aktiv.isChecked(),
            gebiete_je_gewerk,
        )

    def speichern(self) -> None:
        try:
            eingabe = self._eingabe()
            validiere_unternehmen(eingabe, Verwaltung(self.db).gebietsschluessel())
        except Validierungsfehler as exc:
            QMessageBox.warning(self, "Angaben prüfen", str(exc))
            return
        bestaetigung = UnternehmenBestaetigungsdialog(eingabe, self.ausgangseingabe, self)
        if bestaetigung.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            Verwaltung(self.db).speichere_unternehmen(eingabe, self.unternehmen_id)
        except Validierungsfehler as exc:
            QMessageBox.warning(self, "Speichern nicht möglich", str(exc))
            return
        self.accept()


class UnternehmenBestaetigungsdialog(QDialog):
    """Nicht editierbare Zusammenfassung vor dem verbindlichen Speichern."""

    def __init__(
        self,
        eingabe: UnternehmenEingabe,
        ausgangseingabe: UnternehmenEingabe | None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Unternehmen verbindlich speichern")
        self.setMinimumWidth(560)

        form = QFormLayout()
        form.addRow("Unternehmen:", self._wert(eingabe.name))
        form.addRow("PPS-Nummer:", self._wert(eingabe.pps_nummer))
        form.addRow("Aktivstatus:", self._wert("Aktiv" if eingabe.aktiv else "Inaktiv"))

        zuordnungen = QTableWidget(len(eingabe.gebiete_je_gewerk), 2)
        zuordnungen.setHorizontalHeaderLabels(["Gewerk", "Ausgewählte Gebiete"])
        zuordnungen.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        zuordnungen.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        zuordnungen.verticalHeader().setVisible(False)
        zuordnungen.horizontalHeader().setStretchLastSection(True)
        for zeile, (gewerk, gebiete) in enumerate(sorted(eingabe.gebiete_je_gewerk.items())):
            zuordnungen.setItem(zeile, 0, _item(gewerk))
            zuordnungen.setItem(zeile, 1, _item(", ".join(sorted(gebiete))))
        zuordnungen.resizeColumnsToContents()
        zuordnungen.setMinimumHeight(min(260, 70 + 30 * len(eingabe.gebiete_je_gewerk)))

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Bitte prüfen Sie die folgenden Angaben:"))
        layout.addLayout(form)
        layout.addWidget(QLabel("Gewerke und Gebiete:"))
        layout.addWidget(zuordnungen)

        if ausgangseingabe is not None:
            a_gewerke = set(ausgangseingabe.gebiete_je_gewerk)
            n_gewerke = set(eingabe.gebiete_je_gewerk)
            a_gebiete = self._zuordnungen(ausgangseingabe)
            n_gebiete = self._zuordnungen(eingabe)
            aenderungen = QFormLayout()
            aenderungen.addRow("Hinzugefügte Gewerke:", self._wert_liste(n_gewerke - a_gewerke))
            aenderungen.addRow("Entfernte Gewerke:", self._wert_liste(a_gewerke - n_gewerke))
            aenderungen.addRow("Hinzugefügte Gebiete:", self._wert_liste(n_gebiete - a_gebiete))
            aenderungen.addRow("Entfernte Gebiete:", self._wert_liste(a_gebiete - n_gebiete))
            layout.addWidget(QLabel("Änderungen gegenüber dem geladenen Stand:"))
            layout.addLayout(aenderungen)

        buttons = QDialogButtonBox()
        zurueck = buttons.addButton("Zurück zum Bearbeiten", QDialogButtonBox.ButtonRole.RejectRole)
        speichern = buttons.addButton("Verbindlich speichern", QDialogButtonBox.ButtonRole.AcceptRole)
        zurueck.clicked.connect(self.reject)
        speichern.clicked.connect(self.accept)
        speichern.setDefault(True)
        layout.addWidget(buttons)

    @staticmethod
    def _wert(text: str) -> QLabel:
        label = QLabel(text)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setWordWrap(True)
        return label

    @classmethod
    def _wert_liste(cls, werte: set[str]) -> QLabel:
        return cls._wert("\n".join(sorted(werte)) if werte else "–")

    @staticmethod
    def _zuordnungen(eingabe: UnternehmenEingabe) -> set[str]:
        return {
            f"{gewerk}: {gebiet}"
            for gewerk, gebiete in eingabe.gebiete_je_gewerk.items()
            for gebiet in gebiete
        }


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
