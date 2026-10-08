"""Click-through subtitle banner drawn over the game."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QPainter, QPainterPath
from PySide6.QtWidgets import QWidget

WIDTH_RATIO = 0.7
MAX_HEIGHT_RATIO = 0.45  # never cover more than this much of the screen
MARGIN = 40
PAD_X, PAD_Y, GAP = 22, 14, 8
TRANSLATION_SIZES = (26, 24, 22, 20, 18, 16)
ORIGINAL_SIZE_RATIO = 0.68
TEXT_FLAGS = Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap


@dataclass(frozen=True)
class BannerLayout:
    height: int
    translation_px: int
    translation_h: int
    original_px: int
    original_h: int  # 0 when the original is not shown


def _font(px: int) -> QFont:
    font = QFont()
    font.setPixelSize(px)
    return font


def _text_height(text: str, px: int, width: int) -> int:
    if not text:
        return 0
    rect = QFontMetrics(_font(px)).boundingRect(QRect(0, 0, width, 1_000_000), TEXT_FLAGS, text)
    return rect.height()


def fit_layout(original: str, translation: str, width: int, max_height: int,
               show_original: bool = True) -> BannerLayout:
    """Largest font that fits: with the original first, then translation only, then clip."""
    inner = max(width - 2 * PAD_X, 50)
    attempts = [(True, px) for px in TRANSLATION_SIZES] if show_original and original else []
    attempts += [(False, px) for px in TRANSLATION_SIZES]
    layout = None
    for with_original, px in attempts:
        tr_h = _text_height(translation, px, inner)
        orig_px = max(int(px * ORIGINAL_SIZE_RATIO), 12)
        orig_h = _text_height(original, orig_px, inner) if with_original else 0
        height = 2 * PAD_Y + tr_h + (orig_h + GAP if orig_h else 0)
        layout = BannerLayout(min(height, max_height), px, tr_h, orig_px, orig_h)
        if height <= max_height:
            return layout
    return layout  # smallest translation-only layout, clipped to max_height


class Banner(QWidget):
    """Override-redirect, input-transparent window (X11 / XWayland).

    The window manager ignores it, so it stays above fullscreen games on X11.
    Its height follows the text; long text gets a smaller font, then loses the
    original line, and is finally clipped at MAX_HEIGHT_RATIO of the screen.
    """

    def __init__(self, position: str = "top", show_original: bool = True) -> None:
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
        self._position = position
        self._show_original = show_original
        self._layout = BannerLayout(2 * PAD_Y, TRANSLATION_SIZES[0], 0, 16, 0)
        self._relayout()

    def set_position(self, position: str) -> None:
        self._position = position
        self._relayout()

    def set_show_original(self, show: bool) -> None:
        self._show_original = show
        self._relayout()

    def show_line(self, original: str, translation: str) -> None:
        self._original, self._translation = original, translation
        self._relayout()
        if not self.isVisible():
            self.show()
        self.raise_()
        self.update()

    def _relayout(self) -> None:
        screen = QGuiApplication.primaryScreen().geometry()
        width = int(screen.width() * WIDTH_RATIO)
        self._layout = fit_layout(self._original, self._translation, width,
                                  int(screen.height() * MAX_HEIGHT_RATIO), self._show_original)
        height = self._layout.height
        x = screen.x() + (screen.width() - width) // 2
        if self._position == "top":
            y = screen.y() + MARGIN
        else:
            y = screen.y() + screen.height() - height - MARGIN
        self.setGeometry(x, y, width, height)

    def frame_rect(self, frame_w: int, frame_h: int) -> tuple[int, int, int, int]:
        """This banner's area in captured-frame pixels, for masking it out of OCR."""
        geo: QRect = QGuiApplication.primaryScreen().geometry()
        sx = frame_w / max(geo.width(), 1)
        sy = frame_h / max(geo.height(), 1)
        g = self.geometry()
        return (int((g.x() - geo.x()) * sx), int((g.y() - geo.y()) * sy),
                int((g.right() + 1 - geo.x()) * sx), int((g.bottom() + 1 - geo.y()) * sy))

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt naming)
        layout = self._layout
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(box, 14, 14)
        p.fillPath(path, QColor(0, 0, 0, 185))
        p.setClipPath(path)

        top = box.top() + PAD_Y
        width = box.width() - 2 * PAD_X
        if layout.original_h:
            p.setFont(_font(layout.original_px))
            p.setPen(QColor(185, 185, 185))
            p.drawText(QRectF(box.left() + PAD_X, top, width, layout.original_h),
                       TEXT_FLAGS, self._original)
            top += layout.original_h + GAP
        p.setFont(_font(layout.translation_px))
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(box.left() + PAD_X, top, width, layout.translation_h),
                   TEXT_FLAGS, self._translation)
