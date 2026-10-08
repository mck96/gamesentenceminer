"""Preview of the captured frame with text regions drawn on top (OBS-style)."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
)

from gamesentenceminer.regions import Region

PALETTE = ["#4cc9f0", "#f72585", "#ffd166", "#06d6a0", "#b388ff", "#ff9e40"]
MIN_SIZE = 8.0
HANDLE_PX = 14.0  # resize handle size on screen


class RegionItem(QGraphicsRectItem):
    def __init__(self, name: str, rect: QRectF, color: QColor, canvas: FrameCanvas) -> None:
        super().__init__(QRectF(0, 0, rect.width(), rect.height()))
        self.name = name
        self._canvas = canvas
        self._resizing = False
        self.setPos(rect.topLeft())
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
                      | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                      | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        pen = QPen(color, 2)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setBrush(QColor(color.red(), color.green(), color.blue(), 45))
        label = QGraphicsSimpleTextItem(name, self)
        font = QFont()
        font.setPixelSize(13)
        font.setBold(True)
        label.setFont(font)
        label.setBrush(QBrush(color))
        label.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        label.setPos(0, 0)  # inside the top-left corner, constant size on screen

    def scene_box(self) -> QRectF:
        return QRectF(self.pos(), self.rect().size())

    def _handle(self) -> float:
        return HANDLE_PX / max(self._canvas.zoom(), 1e-6)

    def _in_handle(self, pos: QPointF) -> bool:
        r, hs = self.rect(), self._handle()
        return pos.x() >= r.right() - hs and pos.y() >= r.bottom() - hs

    def hoverMoveEvent(self, event) -> None:  # noqa: N802
        self.setCursor(Qt.CursorShape.SizeFDiagCursor if self._in_handle(event.pos())
                       else Qt.CursorShape.SizeAllCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._in_handle(event.pos()):
            self._resizing = True
            self.setSelected(True)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._resizing:
            bounds = self.scene().sceneRect()
            w = min(max(event.pos().x(), MIN_SIZE), bounds.right() - self.pos().x())
            h = min(max(event.pos().y(), MIN_SIZE), bounds.bottom() - self.pos().y())
            self.setRect(QRectF(0, 0, w, h))
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._resizing = False
        super().mouseReleaseEvent(event)
        self._canvas.region_changed.emit(self.name, self.scene_box())

    def itemChange(self, change, value):  # noqa: N802
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            bounds = self.scene().sceneRect()
            r = self.rect()
            x = min(max(value.x(), bounds.left()), bounds.right() - r.width())
            y = min(max(value.y(), bounds.top()), bounds.bottom() - r.height())
            return QPointF(x, y)
        return super().itemChange(change, value)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        super().paint(painter, option, widget)
        if self.isSelected():
            hs = self._handle()
            r = self.rect()
            painter.fillRect(QRectF(r.right() - hs, r.bottom() - hs, hs, hs), self.pen().color())


class FrameCanvas(QGraphicsView):
    region_drawn = Signal(QRectF)  # in source pixels
    region_changed = Signal(str, QRectF)
    region_selected = Signal(object)  # name or None
    delete_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setBackgroundBrush(QColor(24, 24, 28))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMinimumSize(480, 270)
        self._pixmap = self.scene().addPixmap(QPixmap())
        self._pixmap.setZValue(-1)
        self._source_size: tuple[int, int] | None = None
        self._items: dict[str, RegionItem] = {}
        self._rubber: QGraphicsRectItem | None = None
        self._rubber_origin = QPointF()
        self.placeholder = "Kaynak yok: 'Yakalamayı başlat'a bas"
        self.scene().selectionChanged.connect(self._on_selection_changed)

    # -- frame -----------------------------------------------------------------

    def set_frame(self, frame: np.ndarray, scale: int = 1) -> bool:
        """Show a BGRx frame; `scale` = source pixels per frame pixel. True if size changed."""
        frame = np.ascontiguousarray(frame)
        h, w = frame.shape[:2]
        image = QImage(frame.data, w, h, frame.strides[0], QImage.Format.Format_RGB32)
        self._pixmap.setPixmap(QPixmap.fromImage(image))
        self._pixmap.setScale(scale)
        size = (w * scale, h * scale)
        if size == self._source_size:
            return False
        self._source_size = size
        self.scene().setSceneRect(0, 0, *size)
        self.fit()
        return True

    def source_size(self) -> tuple[int, int] | None:
        return self._source_size

    def zoom(self) -> float:
        return self.transform().m11() or 1.0

    def fit(self) -> None:
        if self._source_size:
            self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.fit()

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:  # noqa: N802
        if self._source_size is None:
            painter.resetTransform()
            painter.setPen(QColor(150, 150, 150))
            painter.drawText(self.viewport().rect(), Qt.AlignmentFlag.AlignCenter,
                             self.placeholder)

    # -- regions ---------------------------------------------------------------

    def set_regions(self, regions: list[Region], selected: str | None = None) -> None:
        self.scene().blockSignals(True)
        for item in self._items.values():
            self.scene().removeItem(item)
        self._items.clear()
        if self._source_size:
            sw, sh = self._source_size
            for i, region in enumerate(regions):
                x, y, w, h = region.rect
                color = QColor(PALETTE[i % len(PALETTE)])
                item = RegionItem(region.name, QRectF(x * sw, y * sh, w * sw, h * sh), color, self)
                self.scene().addItem(item)
                item.setSelected(region.name == selected)
                self._items[region.name] = item
        self.scene().blockSignals(False)

    def select(self, name: str | None) -> None:
        for item_name, item in self._items.items():
            item.setSelected(item_name == name)

    def _on_selection_changed(self) -> None:
        selected = [i for i in self.scene().selectedItems() if isinstance(i, RegionItem)]
        self.region_selected.emit(selected[0].name if selected else None)

    def normalized(self, rect: QRectF) -> tuple[float, float, float, float]:
        sw, sh = self._source_size or (1, 1)
        return (rect.x() / sw, rect.y() / sh, rect.width() / sw, rect.height() / sh)

    # -- drawing new regions -----------------------------------------------------

    def _region_at(self, pos) -> RegionItem | None:
        item = self.itemAt(pos)
        while item is not None and not isinstance(item, RegionItem):
            item = item.parentItem()
        return item

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if (event.button() == Qt.MouseButton.LeftButton and self._source_size
                and self._region_at(event.position().toPoint()) is None):
            self.scene().clearSelection()
            self._rubber_origin = self._clamp(self.mapToScene(event.position().toPoint()))
            pen = QPen(QColor("#ffffff"), 1, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            self._rubber = self.scene().addRect(QRectF(self._rubber_origin, self._rubber_origin),
                                                pen, QColor(255, 255, 255, 30))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._rubber is not None:
            point = self._clamp(self.mapToScene(event.position().toPoint()))
            self._rubber.setRect(QRectF(self._rubber_origin, point).normalized())
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._rubber is not None:
            rect = self._rubber.rect()
            self.scene().removeItem(self._rubber)
            self._rubber = None
            if rect.width() >= MIN_SIZE and rect.height() >= MIN_SIZE:
                self.region_drawn.emit(rect)
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            for item in self.scene().selectedItems():
                if isinstance(item, RegionItem):
                    self.delete_requested.emit(item.name)
            return
        super().keyPressEvent(event)

    def _clamp(self, p: QPointF) -> QPointF:
        r = self.scene().sceneRect()
        return QPointF(min(max(p.x(), r.left()), r.right()), min(max(p.y(), r.top()), r.bottom()))
