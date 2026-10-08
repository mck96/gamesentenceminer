"""Entry point: `uv run gsm`."""

from __future__ import annotations

import argparse
import os
import signal
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gsm", description="Game screen OCR + translation")
    parser.add_argument("--max-fps", type=int, help="frames per second taken from the screen")
    parser.add_argument("--fake-source", type=lambda s: [Path(p) for p in s.split(",")],
                        help="development: replay these images instead of capturing")
    args = parser.parse_args(argv)

    # The overlay needs X11 window semantics (override-redirect, stays on top);
    # on a Wayland session this runs through XWayland.
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    from PySide6.QtWidgets import QApplication

    from gamesentenceminer.editor.window import MainWindow

    app = QApplication(sys.argv[:1])
    app.setApplicationName("gamesentenceminer")
    window = MainWindow(fake_source=args.fake_source, max_fps=args.max_fps)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
