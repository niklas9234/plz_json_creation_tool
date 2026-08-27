from __future__ import annotations

import json
from collections.abc import Mapping

from PySide6.QtCore import QEvent, QPointF, Qt, Signal
from PySide6.QtGui import QColor, QBrush, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsPolygonItem, QGraphicsScene, QGraphicsView, QVBoxLayout, QWidget


class Gebietskarte(QWidget):
    """Kartenansicht für Gebietszuordnungen, wahlweise ohne Eingabemöglichkeit."""

    gebietAngeklickt = Signal(str)
    _farben = ("#2563eb", "#dc2626", "#16a34a", "#9333ea", "#ea580c", "#0891b2")

    def __init__(self, nur_lesen: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.nur_lesen = nur_lesen
        self._sichtbar: set[str] = set()
        self._zuordnungen: dict[str, set[str]] = {}
        self._geometrien: dict[str, object] = {}
        self.szene = QGraphicsScene(self)
        self.ansicht = QGraphicsView(self.szene)
        self.ansicht.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.ansicht.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.ansicht.viewport().installEventFilter(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ansicht)

    def set_zuordnungen(self, zuordnungen: Mapping[str, set[str]], geometrien: Mapping[str, object]) -> None:
        self._zuordnungen = {name: set(gebiete) for name, gebiete in zuordnungen.items()}
        self._geometrien = dict(geometrien)
        self._sichtbar = set(zuordnungen)
        self._zeichnen()

    def set_gewerk_sichtbar(self, gewerk: str, sichtbar: bool) -> None:
        (self._sichtbar.add if sichtbar else self._sichtbar.discard)(gewerk)
        self._zeichnen()

    def _zeichnen(self) -> None:
        self.szene.clear()
        farben = {name: QColor(self._farben[index % len(self._farben)]) for index, name in enumerate(self._zuordnungen)}
        for schluessel, geometrie in self._geometrien.items():
            if isinstance(geometrie, str):
                geometrie = json.loads(geometrie)
            namen = [name for name, gebiete in self._zuordnungen.items() if name in self._sichtbar and schluessel in gebiete]
            if not namen:
                continue
            farbe = farben[namen[0]]
            koordinaten = geometrie.get("coordinates", [])
            flaechen = koordinaten if geometrie.get("type") == "MultiPolygon" else [koordinaten]
            for flaeche in flaechen:
                if not flaeche:
                    continue
                polygon = QPolygonF(QPointF(float(x) * 20, -float(y) * 20) for x, y, *_ in flaeche[0])
                item = QGraphicsPolygonItem(polygon)
                item.setBrush(QBrush(QColor(farbe.red(), farbe.green(), farbe.blue(), 150)))
                item.setPen(QPen(farbe.darker(), 0))
                item.setToolTip(f"{schluessel}: {', '.join(namen)}")
                item.setData(0, schluessel)
                self.szene.addItem(item)
        self.szene.setSceneRect(self.szene.itemsBoundingRect())
        if not self.szene.sceneRect().isEmpty():
            self.ansicht.fitInView(self.szene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if watched is self.ansicht.viewport() and event.type() == QEvent.Type.MouseButtonPress and not self.nur_lesen:
            position = self.ansicht.mapToScene(event.position().toPoint())  # type: ignore[attr-defined]
            item = self.szene.itemAt(position, self.ansicht.transform())
            if item is not None and item.data(0):
                self.gebietAngeklickt.emit(str(item.data(0)))
        return super().eventFilter(watched, event)
