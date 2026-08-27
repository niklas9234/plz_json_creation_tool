from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
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
from app.validierung import Validierungsfehler


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


class GebietsauswahlWidget(QWidget):
    """Durchsuchbare Gebietsliste mit einer kompakten Karten-Zusammenfassung."""

    auswahlGeaendert = Signal(set)

    def __init__(self, db: Database, parent: QWidget | None = None):
        super().__init__(parent)
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Gebiet suchen …")
        self.suche.setClearButtonEnabled(True)
        self.gebietsliste = QListWidget()
        self.karte = QLabel("Keine Gebiete ausgewählt")
        self.karte.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.karte.setMinimumHeight(80)
        self.karte.setStyleSheet("QLabel { background: #eef2f5; border: 1px solid #c7cdd1; }")
        with db.connect() as con:
            self._gebiete = [
                (row[0], row[1])
                for row in con.execute("SELECT schluessel, anzeigename FROM gebiete ORDER BY schluessel")
            ]
        self._auswahl: set[str] = set()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Karte"))
        layout.addWidget(self.karte)
        layout.addWidget(self.suche)
        layout.addWidget(self.gebietsliste, 1)
        self.suche.textChanged.connect(self._liste_fuellen)
        self.gebietsliste.itemChanged.connect(self._item_geaendert)
        self._liste_fuellen()

    def set_auswahl(self, gebiete: set[str]) -> None:
        self._auswahl = set(gebiete)
        self._liste_fuellen()
        self._karte_aktualisieren()

    def auswahl(self) -> set[str]:
        return set(self._auswahl)

    def _liste_fuellen(self) -> None:
        text = self.suche.text().strip().casefold()
        with QSignalBlocker(self.gebietsliste):
            self.gebietsliste.clear()
            for schluessel, anzeigename in self._gebiete:
                if text and text not in schluessel.casefold() and text not in anzeigename.casefold():
                    continue
                item = QListWidgetItem(f"{schluessel} · {anzeigename}")
                item.setData(Qt.ItemDataRole.UserRole, schluessel)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(
                    Qt.CheckState.Checked if schluessel in self._auswahl else Qt.CheckState.Unchecked
                )
                self.gebietsliste.addItem(item)

    def _item_geaendert(self, item: QListWidgetItem) -> None:
        schluessel = item.data(Qt.ItemDataRole.UserRole)
        if item.checkState() == Qt.CheckState.Checked:
            self._auswahl.add(schluessel)
        else:
            self._auswahl.discard(schluessel)
        self._karte_aktualisieren()
        self.auswahlGeaendert.emit(set(self._auswahl))

    def _karte_aktualisieren(self) -> None:
        if self._auswahl:
            self.karte.setText("Ausgewählt: " + ", ".join(sorted(self._auswahl)))
        else:
            self.karte.setText("Keine Gebiete ausgewählt")


class GewerkAuswahlDialog(QDialog):
    """Suchdialog für bereits in der Datenbank vorhandene Gewerke."""

    def __init__(self, namen: list[str], parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Gewerk hinzufügen")
        self.setMinimumWidth(360)
        self.auswahl: str | None = None
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Vorhandene Gewerke durchsuchen …")
        self.suche.setClearButtonEnabled(True)
        self.liste = QListWidget()
        self._namen = namen
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Hinzufügen")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Abbrechen")
        buttons.accepted.connect(self._annehmen)
        buttons.rejected.connect(self.reject)
        self.suche.textChanged.connect(self._fuellen)
        self.liste.itemDoubleClicked.connect(lambda _item: self._annehmen())
        layout = QVBoxLayout(self)
        layout.addWidget(self.suche)
        layout.addWidget(self.liste)
        layout.addWidget(buttons)
        self._fuellen()

    def _fuellen(self) -> None:
        text = self.suche.text().strip().casefold()
        self.liste.clear()
        self.liste.addItems(name for name in self._namen if text in name.casefold())
        if self.liste.count():
            self.liste.setCurrentRow(0)

    def _annehmen(self) -> None:
        if self.liste.currentItem() is None:
            return
        self.auswahl = self.liste.currentItem().text()
        self.accept()


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
        self.gebiete_je_gewerk: dict[str, set[str]] = {}
        self.gespeicherte_gebiete_je_gewerk: dict[str, set[str]] = {}
        self.ausgewaehltes_gewerk: str | None = None
        # Kompatibilität für Aufrufer der früheren Textfeld-API; das Feld wird
        # nicht mehr angezeigt und nur bei explizit gesetztem Inhalt ausgewertet.
        self.zuordnungen = QPlainTextEdit()

        self.gewerke_liste = QListWidget()
        self.gewerke_liste.setMinimumWidth(220)
        self.gewerke_liste.currentItemChanged.connect(self._gewerk_gewechselt)
        self.gewerk_hinzufuegen_button = QPushButton("Gewerk hinzufügen")
        self.gewerk_entfernen_button = QPushButton("Gewerk entfernen")
        self.neues_gewerk_button = QPushButton("Neues Gewerk anlegen")
        self.gewerk_hinzufuegen_button.clicked.connect(self.gewerk_hinzufuegen)
        self.gewerk_entfernen_button.clicked.connect(self.gewerk_entfernen)
        self.neues_gewerk_button.clicked.connect(self.neues_gewerk_anlegen)

        gewerke_seite = QVBoxLayout()
        gewerke_seite.addWidget(QLabel("Gewerke"))
        gewerke_seite.addWidget(self.gewerke_liste, 1)
        gewerke_seite.addWidget(self.gewerk_hinzufuegen_button)
        gewerke_seite.addWidget(self.gewerk_entfernen_button)
        gewerke_seite.addWidget(self.neues_gewerk_button)

        self.gebietsauswahl = GebietsauswahlWidget(db)
        self.gebietsauswahl.auswahlGeaendert.connect(self._gebietsauswahl_geaendert)
        zuordnungs_layout = QHBoxLayout()
        zuordnungs_layout.addLayout(gewerke_seite)
        zuordnungs_layout.addWidget(self.gebietsauswahl, 1)

        form = QFormLayout()
        form.addRow("Unternehmen:", self.name)
        form.addRow("PPS-Nummer:", self.pps_nummer)
        form.addRow("Status:", self.aktiv)
        hinweis = QLabel("Wählen Sie links ein Gewerk und rechts dessen Gebiete aus.")
        hinweis.setWordWrap(True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Speichern")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Abbrechen")
        buttons.accepted.connect(self.speichern)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(zuordnungs_layout, 1)
        layout.addWidget(hinweis)
        layout.addWidget(buttons)
        if unternehmen_id is not None:
            self._laden()
        self._gewerkliste_aktualisieren()

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
        self.gebiete_je_gewerk = {
            r[0]: {gebiet.strip() for gebiet in (r[1] or "").split(",") if gebiet.strip()}
            for r in zuordnungen
        }
        self.gespeicherte_gebiete_je_gewerk = {
            name: set(gebiete) for name, gebiete in self.gebiete_je_gewerk.items()
        }

    def _gewerkliste_aktualisieren(self, auswaehlen: str | None = None) -> None:
        auswaehlen = auswaehlen or self.ausgewaehltes_gewerk
        with QSignalBlocker(self.gewerke_liste):
            self.gewerke_liste.clear()
            for name, gebiete in self.gebiete_je_gewerk.items():
                einheit = "Gebiet" if len(gebiete) == 1 else "Gebiete"
                item = QListWidgetItem(f"{name} · {len(gebiete)} {einheit}")
                item.setData(Qt.ItemDataRole.UserRole, name)
                if self.gespeicherte_gebiete_je_gewerk.get(name) != gebiete:
                    font = QFont(item.font())
                    font.setBold(True)
                    item.setFont(font)
                    item.setForeground(QColor("#b35c00"))
                    item.setToolTip("Ungespeicherte Änderungen")
                self.gewerke_liste.addItem(item)
                if name == auswaehlen:
                    self.gewerke_liste.setCurrentItem(item)
        if self.gewerke_liste.currentItem() is None and self.gewerke_liste.count():
            self.gewerke_liste.setCurrentRow(0)
        self._gewerk_gewechselt(self.gewerke_liste.currentItem(), None)

    def _gewerk_gewechselt(self, aktuell: QListWidgetItem | None, _vorher: QListWidgetItem | None) -> None:
        self.ausgewaehltes_gewerk = aktuell.data(Qt.ItemDataRole.UserRole) if aktuell else None
        self.gebietsauswahl.set_auswahl(self.gebiete_je_gewerk.get(self.ausgewaehltes_gewerk, set()))

    def _gebietsauswahl_geaendert(self, gebiete: set[str]) -> None:
        if self.ausgewaehltes_gewerk is None:
            return
        self.gebiete_je_gewerk[self.ausgewaehltes_gewerk] = set(gebiete)
        self._gewerkliste_aktualisieren(self.ausgewaehltes_gewerk)

    def gewerk_hinzufuegen(self) -> None:
        with self.db.connect() as con:
            namen = [
                row[0]
                for row in con.execute("SELECT name FROM gewerke WHERE aktiv=1 ORDER BY name COLLATE NOCASE")
            ]
        namen = [name for name in namen if name not in self.gebiete_je_gewerk]
        if not namen:
            QMessageBox.information(self, "Gewerk hinzufügen", "Es sind keine weiteren vorhandenen Gewerke verfügbar.")
            return
        dialog = GewerkAuswahlDialog(namen, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.auswahl:
            self.gebiete_je_gewerk[dialog.auswahl] = set()
            self._gewerkliste_aktualisieren(dialog.auswahl)

    def neues_gewerk_anlegen(self) -> None:
        name, ok = QInputDialog.getText(self, "Neues Gewerk anlegen", "Name des neuen Gewerks:")
        name = name.strip()
        if not ok or not name:
            return
        if any(name.casefold() == vorhanden.casefold() for vorhanden in self.gebiete_je_gewerk):
            QMessageBox.information(self, "Neues Gewerk anlegen", "Dieses Gewerk wurde bereits hinzugefügt.")
            return
        with self.db.connect() as con:
            vorhanden = con.execute("SELECT name FROM gewerke WHERE name=? COLLATE NOCASE", (name,)).fetchone()
        if vorhanden:
            QMessageBox.information(
                self, "Neues Gewerk anlegen", "Dieses Gewerk ist bereits vorhanden. Verwenden Sie „Gewerk hinzufügen“."
            )
            return
        self.gebiete_je_gewerk[name] = set()
        self._gewerkliste_aktualisieren(name)

    def gewerk_entfernen(self) -> None:
        name = self.ausgewaehltes_gewerk
        if name is None:
            return
        if self.gebiete_je_gewerk[name]:
            antwort = QMessageBox.question(
                self,
                "Gewerk entfernen",
                f"„{name}“ sind bereits Gebiete zugeordnet. Soll das Gewerk wirklich entfernt werden?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if antwort != QMessageBox.StandardButton.Yes:
                return
        del self.gebiete_je_gewerk[name]
        self.ausgewaehltes_gewerk = None
        self._gewerkliste_aktualisieren()

    def _eingabe(self) -> UnternehmenEingabe:
        gebiete_je_gewerk = self.gebiete_je_gewerk
        if self.zuordnungen.toPlainText().strip():
            gebiete_je_gewerk = {}
            for nummer, zeile in enumerate(self.zuordnungen.toPlainText().splitlines(), 1):
                if not zeile.strip():
                    continue
                if ":" not in zeile:
                    raise Validierungsfehler(
                        f"In Zeile {nummer} fehlt der Doppelpunkt zwischen Gewerk und Gebieten."
                    )
                gewerk, gebiete = zeile.split(":", 1)
                gebiete_je_gewerk[gewerk.strip()] = {
                    gebiet.strip() for gebiet in gebiete.split(",") if gebiet.strip()
                }
        return UnternehmenEingabe(
            self.name.text(), self.pps_nummer.text(), self.aktiv.isChecked(), gebiete_je_gewerk
        )

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
