from __future__ import annotations

import json

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
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


class _GebietsPfad(QGraphicsPathItem):
    """Klickbares Kartenobjekt; die eigentliche Auswahl verwaltet das Widget."""

    def __init__(self, schluessel: str, path: QPainterPath, umschalten):
        super().__init__(path)
        self.setData(0, schluessel)
        self._umschalten = umschalten
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._umschalten(str(self.data(0)))
            event.accept()
            return
        super().mousePressEvent(event)


class GebietsAuswahlWidget(QWidget):
    """Barrierearm synchronisierte Gewerk-, Karten- und Gebietsauswahl."""

    NICHT_AUSGEWAEHLT = QColor("#d7e3ea")
    AUSGEWAEHLT = QColor("#25854a")
    FOKUS = QColor("#f39c12")

    def __init__(self, db: Database, parent: QWidget | None = None):
        super().__init__(parent)
        self._auswahl: dict[str, set[str]] = {}
        self._gebiete: dict[str, tuple[str, dict]] = {}
        self._kartenobjekte: dict[str, QGraphicsPathItem] = {}
        self._aktualisiere = False

        self.gewerke = QListWidget()
        self.gewerke.setAccessibleName("Zugeordnete Gewerke")
        self.gewerke.setMinimumWidth(160)
        self.gewerke.currentItemChanged.connect(self._gewerk_gewechselt)
        self.gewerke.itemChanged.connect(self._gewerk_status_geaendert)

        self.szene = QGraphicsScene(self)
        self.karte = QGraphicsView(self.szene)
        self.karte.setAccessibleName("Gebietskarte")
        self.karte.setMinimumSize(360, 300)
        self.karte.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.karte.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)

        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Gebiet suchen …")
        self.suche.setClearButtonEnabled(True)
        self.suche.textChanged.connect(self._filtern)
        self.gebietsliste = QListWidget()
        self.gebietsliste.setAccessibleName("Gebiete auswählen")
        self.gebietsliste.itemChanged.connect(self._gebiet_status_geaendert)
        self.gebietsliste.currentItemChanged.connect(self._gebiet_fokussiert)
        alle = QPushButton("Alle auswählen")
        keine = QPushButton("Auswahl aufheben")
        alle.clicked.connect(lambda: self._sichtbare_setzen(True))
        keine.clicked.connect(lambda: self._sichtbare_setzen(False))
        rechts = QVBoxLayout()
        rechts.addWidget(self.suche)
        rechts.addWidget(self.gebietsliste, 1)
        rechts.addWidget(alle)
        rechts.addWidget(keine)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.gewerke)
        layout.addWidget(self.karte, 1)
        layout.addLayout(rechts)
        self._daten_laden()

    @property
    def auswahl(self) -> dict[str, set[str]]:
        return {name: set(gebiete) for name, gebiete in self._auswahl.items()}

    def set_auswahl(self, auswahl: dict[str, set[str]]) -> None:
        self._auswahl = {name: set(gebiete) for name, gebiete in auswahl.items()}
        bekannte = {self.gewerke.item(i).text() for i in range(self.gewerke.count())}
        for name in sorted(self._auswahl, key=str.casefold):
            if name not in bekannte:
                self._gewerk_hinzufuegen(name)
        self._aktualisiere = True
        for i in range(self.gewerke.count()):
            item = self.gewerke.item(i)
            item.setCheckState(Qt.CheckState.Checked if item.text() in self._auswahl else Qt.CheckState.Unchecked)
        self._aktualisiere = False
        if self.gewerke.currentItem() is None and self.gewerke.count():
            self.gewerke.setCurrentRow(0)
        self._ansicht_aktualisieren()

    def _daten_laden(self) -> None:
        with self.db.connect() as con:
            gewerke = con.execute("SELECT name FROM gewerke ORDER BY name COLLATE NOCASE").fetchall()
            gebiete = con.execute(
                "SELECT schluessel, anzeigename, geometrie FROM gebiete ORDER BY anzeigename COLLATE NOCASE, schluessel"
            ).fetchall()
        for (name,) in gewerke:
            self._gewerk_hinzufuegen(name)
        for schluessel, anzeigename, geometrie in gebiete:
            geometry = json.loads(geometrie)
            self._gebiete[schluessel] = (anzeigename, geometry)
            tooltip = f"{schluessel} – {anzeigename}"
            item = QListWidgetItem(tooltip)
            item.setData(Qt.ItemDataRole.UserRole, schluessel)
            item.setToolTip(tooltip)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.gebietsliste.addItem(item)
            kartenobjekt = _GebietsPfad(schluessel, self._pfad(geometry), self._karte_umschalten)
            kartenobjekt.setToolTip(tooltip)
            kartenobjekt.setPen(QPen(QColor("#526773"), 0))
            self.szene.addItem(kartenobjekt)
            self._kartenobjekte[schluessel] = kartenobjekt
        if self.szene.itemsBoundingRect().isValid():
            self.karte.fitInView(self.szene.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)
        if self.gewerke.count():
            self.gewerke.setCurrentRow(0)
        self._ansicht_aktualisieren()

    def _gewerk_hinzufuegen(self, name: str) -> None:
        item = QListWidgetItem(name)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Unchecked)
        self.gewerke.addItem(item)

    @staticmethod
    def _pfad(geometry: dict) -> QPainterPath:
        path = QPainterPath()
        path.setFillRule(Qt.FillRule.OddEvenFill)
        polygons = [geometry["coordinates"]] if geometry.get("type") == "Polygon" else geometry.get("coordinates", [])
        for polygon in polygons:
            for ring in polygon:
                if not ring:
                    continue
                path.moveTo(QPointF(float(ring[0][0]), -float(ring[0][1])))
                for coordinate in ring[1:]:
                    path.lineTo(QPointF(float(coordinate[0]), -float(coordinate[1])))
                path.closeSubpath()
        return path

    def _aktuelles_gewerk(self) -> str | None:
        item = self.gewerke.currentItem()
        return item.text() if item is not None else None

    def _gewerk_gewechselt(self, *_args) -> None:
        self._ansicht_aktualisieren()

    def _gewerk_status_geaendert(self, item: QListWidgetItem) -> None:
        if self._aktualisiere:
            return
        if item.checkState() == Qt.CheckState.Checked:
            self._auswahl.setdefault(item.text(), set())
            self.gewerke.setCurrentItem(item)
        else:
            self._auswahl.pop(item.text(), None)
        self._ansicht_aktualisieren()

    def _gebiet_status_geaendert(self, item: QListWidgetItem) -> None:
        if self._aktualisiere:
            return
        gewerk = self._aktuelles_gewerk()
        if gewerk is None:
            return
        self._auswahl.setdefault(gewerk, set())
        self._aktualisiere = True
        self.gewerke.currentItem().setCheckState(Qt.CheckState.Checked)
        self._aktualisiere = False
        schluessel = str(item.data(Qt.ItemDataRole.UserRole))
        if item.checkState() == Qt.CheckState.Checked:
            self._auswahl[gewerk].add(schluessel)
        else:
            self._auswahl[gewerk].discard(schluessel)
        self._farben_aktualisieren()

    def _karte_umschalten(self, schluessel: str) -> None:
        for i in range(self.gebietsliste.count()):
            item = self.gebietsliste.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == schluessel:
                item.setCheckState(Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked)
                self.gebietsliste.setCurrentItem(item)
                break

    def _ansicht_aktualisieren(self) -> None:
        ausgewaehlt = self._auswahl.get(self._aktuelles_gewerk() or "", set())
        self._aktualisiere = True
        for i in range(self.gebietsliste.count()):
            item = self.gebietsliste.item(i)
            item.setCheckState(Qt.CheckState.Checked if item.data(Qt.ItemDataRole.UserRole) in ausgewaehlt else Qt.CheckState.Unchecked)
        self._aktualisiere = False
        self._farben_aktualisieren()

    def _farben_aktualisieren(self) -> None:
        ausgewaehlt = self._auswahl.get(self._aktuelles_gewerk() or "", set())
        fokus = self.gebietsliste.currentItem()
        fokus_key = fokus.data(Qt.ItemDataRole.UserRole) if fokus else None
        for schluessel, item in self._kartenobjekte.items():
            farbe = self.FOKUS if schluessel == fokus_key else self.AUSGEWAEHLT if schluessel in ausgewaehlt else self.NICHT_AUSGEWAEHLT
            item.setBrush(QBrush(farbe))

    def _gebiet_fokussiert(self, *_args) -> None:
        self._farben_aktualisieren()

    def _filtern(self, text: str) -> None:
        text = text.strip().casefold()
        for i in range(self.gebietsliste.count()):
            item = self.gebietsliste.item(i)
            item.setHidden(text not in item.text().casefold())

    def _sichtbare_setzen(self, auswaehlen: bool) -> None:
        status = Qt.CheckState.Checked if auswaehlen else Qt.CheckState.Unchecked
        for i in range(self.gebietsliste.count()):
            item = self.gebietsliste.item(i)
            if not item.isHidden():
                item.setCheckState(status)


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
        self.setMinimumSize(980, 560)
        self.name = QLineEdit()
        self.pps_nummer = QLineEdit()
        self.aktiv = QCheckBox("Aktiv")
        self.aktiv.setChecked(True)
        self.gebietsauswahl = GebietsAuswahlWidget(db)

        form = QFormLayout()
        form.addRow("Unternehmen:", self.name)
        form.addRow("PPS-Nummer:", self.pps_nummer)
        form.addRow("Status:", self.aktiv)
        form.addRow("Gewerke und Gebiete:", self.gebietsauswahl)
        hinweis = QLabel("Gewerk links aktivieren, Gebiet per Karte oder Checkbox auswählen. Die Suche und Schaltflächen wirken auf die sichtbaren Gebiete.")
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
        layout.addWidget(self.karte)
        layout.addWidget(buttons)
        if unternehmen_id is not None:
            self._laden()
        self._gewerkliste_aktualisieren()

    def _laden(self) -> None:
        with self.db.connect() as con:
            row = con.execute("SELECT name, pps_nummer, aktiv FROM unternehmen WHERE id=?", (self.unternehmen_id,)).fetchone()
            zuordnungen = con.execute(
                """SELECT g.name, z.gebiet_schluessel
                   FROM unternehmen_gewerke ug JOIN gewerke g ON g.id=ug.gewerk_id
                   LEFT JOIN gebietszuordnungen z ON z.unternehmen_id=ug.unternehmen_id AND z.gewerk_id=ug.gewerk_id
                   WHERE ug.unternehmen_id=? ORDER BY g.name COLLATE NOCASE, z.gebiet_schluessel""",
                (self.unternehmen_id,),
            ).fetchall()
        if row is None:
            QMessageBox.warning(self, "Nicht gefunden", "Das Unternehmen wurde nicht gefunden.")
            return
        self.name.setText(row[0])
        self.pps_nummer.setText(row[1])
        self.aktiv.setChecked(bool(row[2]))
        auswahl: dict[str, set[str]] = {}
        for gewerk, gebiet in zuordnungen:
            auswahl.setdefault(gewerk, set())
            if gebiet is not None:
                auswahl[gewerk].add(gebiet)
        self.gebietsauswahl.set_auswahl(auswahl)

    def _eingabe(self) -> UnternehmenEingabe:
        return UnternehmenEingabe(
            self.name.text(), self.pps_nummer.text(), self.aktiv.isChecked(), self.gebietsauswahl.auswahl
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
