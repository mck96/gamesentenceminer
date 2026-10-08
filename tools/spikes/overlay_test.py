#!/usr/bin/env python3
"""Phase 0 spike: can a translation banner stay on top of a fullscreen game?

Shows a semi-transparent, click-through subtitle banner at the bottom of the
screen and keeps it updating, so you can switch to a fullscreen game and check:

  1. Is the banner visible on top of the game (and does it stay there)?
  2. Do mouse clicks on the banner reach the game?
  3. Does the game's FPS change?

Modes:
  --platform xcb (default)  run through XWayland, where windows may stay on top
  --platform wayland        native Wayland, expected to lose (for comparison)
  --mode bypass (default)   override-redirect window: ignored by the window manager
  --mode ontop              ordinary always-on-top tool window

Quit with Ctrl+C in the terminal (the banner never takes focus or clicks).
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time

try:
    from PySide6.QtCore import QRectF, Qt, QTimer
    from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPainterPath
    from PySide6.QtWidgets import QApplication, QWidget
except ImportError:
    sys.exit("PySide6 not found: run ./scripts/setup_ubuntu.sh once, then start this with\n"
             "    uv run tools/spikes/overlay_test.py")

SAMPLE_LINES = ("どこへ行くの？   你要去哪里？", "Nereye gidiyorsun?  ·  Where are you going?")


class Banner(QWidget):
    def __init__(self, mode: str, click_through: bool, keep_raising: bool) -> None:
        super().__init__()
        flags = (Qt.WindowType.FramelessWindowHint
                 | Qt.WindowType.WindowStaysOnTopHint
                 | Qt.WindowType.WindowDoesNotAcceptFocus)
        if mode == "bypass":
            flags |= Qt.WindowType.X11BypassWindowManagerHint
        else:
            flags |= Qt.WindowType.Tool
        if click_through:
            flags |= Qt.WindowType.WindowTransparentForInput
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self._header = (f"GSM overlay test · mode={mode} · platform="
                        f"{QGuiApplication.platformName()} · click-through="
                        f"{'on' if click_through else 'off'}")
        self._keep_raising = keep_raising
        self._started = time.monotonic()
        self._ticks = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(250)

    def _tick(self) -> None:
        self._ticks += 1
        self.update()
        if self._keep_raising and self._ticks % 4 == 0:
            self.raise_()

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt naming)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(box, 14, 14)
        p.fillPath(path, QColor(0, 0, 0, 170))

        h = box.height()
        pad = h * 0.08
        small, large = QFont(), QFont()
        small.setPixelSize(max(11, int(h * 0.12)))
        large.setPixelSize(max(14, int(h * 0.2)))

        elapsed = time.monotonic() - self._started
        spinner = "◐◓◑◒"[self._ticks % 4]
        p.setFont(small)
        p.setPen(QColor(190, 190, 190))
        p.drawText(box.adjusted(pad * 2, pad, -pad * 2, 0),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, self._header)
        p.drawText(box.adjusted(pad * 2, pad, -pad * 2, 0),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
                   f"{spinner} {elapsed:6.1f}s")

        p.setFont(large)
        p.setPen(QColor(255, 255, 255))
        line_h = h * 0.3
        for i, line in enumerate(SAMPLE_LINES):
            top = box.top() + h * 0.3 + i * line_h
            p.drawText(QRectF(box.left(), top, box.width(), line_h),
                       Qt.AlignmentFlag.AlignCenter, line)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--platform", choices=("xcb", "wayland"), default="xcb")
    p.add_argument("--mode", choices=("bypass", "ontop"), default="bypass")
    p.add_argument("--no-click-through", action="store_true")
    p.add_argument("--no-raise", action="store_true", help="don't re-raise the banner every second")
    p.add_argument("--screen", type=int, default=0, help="screen index (default 0)")
    p.add_argument("--height", type=int, default=150, help="banner height in pixels")
    p.add_argument("--width", type=float, default=0.7, help="banner width as a screen fraction")
    p.add_argument("--duration", type=float, default=0, help="quit after N seconds (0 = never)")
    args = p.parse_args()

    os.environ["QT_QPA_PLATFORM"] = args.platform
    signal.signal(signal.SIGINT, signal.SIG_DFL)  # Ctrl+C works while Qt's loop runs
    app = QApplication(sys.argv)

    screens = QGuiApplication.screens()
    print(f"session={os.environ.get('XDG_SESSION_TYPE', '?')} "
          f"qt_platform={QGuiApplication.platformName()}")
    for i, s in enumerate(screens):
        g = s.geometry()
        print(f"screen {i}: {s.name()} {g.width()}x{g.height()}+{g.x()}+{g.y()} "
              f"dpr={s.devicePixelRatio():g} refresh={s.refreshRate():.0f}Hz")
    screen = screens[min(args.screen, len(screens) - 1)].geometry()

    banner = Banner(args.mode, not args.no_click_through, not args.no_raise)
    width = int(screen.width() * args.width)
    banner.setGeometry(screen.x() + (screen.width() - width) // 2,
                       screen.y() + screen.height() - args.height - 60, width, args.height)
    banner.show()
    print("banner shown; switch to your fullscreen game. Ctrl+C here to quit.")
    if args.duration > 0:
        QTimer.singleShot(int(args.duration * 1000), app.quit)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
