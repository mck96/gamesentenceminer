"""Click-through subtitle banner drawn over the game."""

from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPainterPath
from PySide6.QtWidgets import QWidget


class Banner(QWidget):
    """Override-redirect, input-transparent window (X11 / XWayland).

    The window manager ignores it, so it stays above fullscreen games on X11.
    """

    def __init__(self, position: str = "top", height: int = 130) -> None:
        super().__init__(None)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.WindowDoesNotAcceptFocus
                            | Qt.WindowType.X11BypassWindowManagerHint
                            | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._original = ""
        self._translation = ""
        self._height = height
        self.set_position(position)

    def set_position(self, position: str) -> None:
        screen = QGuiApplication.primaryScreen().geometry()
        width = int(screen.width() * 0.7)
        x = screen.x() + (screen.width() - width) // 2
        margin = 40
        y = screen.y() + margin if position == "top" else \
            screen.y() + screen.height() - self._height - margin
        self.setGeometry(x, y, width, self._height)

    def show_line(self, original: str, translation: str) -> None:
        self._original, self._translation = original, translation
        if not self.isVisible():
            self.show()
        self.raise_()
        self.update()

    def frame_rect(self, frame_w: int, frame_h: int) -> tuple[int, int, int, int]:
        """This banner's area in captured-frame pixels, for masking it out of OCR."""
        screen = QGuiApplication.primaryScreen()
        geo: QRect = screen.geometry()
        sx = frame_w / max(geo.width(), 1)
        sy = frame_h / max(geo.height(), 1)
        g = self.geometry()
        return (int((g.x() - geo.x()) * sx), int((g.y() - geo.y()) * sy),
                int((g.right() + 1 - geo.x()) * sx), int((g.bottom() + 1 - geo.y()) * sy))

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt naming)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(box, 14, 14)
        p.fillPath(path, QColor(0, 0, 0, 175))
        pad = 18
        inner = box.adjusted(pad, pad * 0.6, -pad, -pad * 0.6)

        small, large = QFont(), QFont()
        small.setPixelSize(17)
        large.setPixelSize(26)
        flags = Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap
        p.setFont(small)
        p.setPen(QColor(185, 185, 185))
        top = QRectF(inner.left(), inner.top(), inner.width(), inner.height() * 0.32)
        p.drawText(top, flags | Qt.AlignmentFlag.AlignTop, self._original)
        p.setFont(large)
        p.setPen(QColor(255, 255, 255))
        bottom = QRectF(inner.left(), top.bottom(), inner.width(), inner.height() - top.height())
        p.drawText(bottom, flags | Qt.AlignmentFlag.AlignVCenter, self._translation)
