"""Stand-in stream that replays still images (development and tests)."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
from PIL import Image


def load_bgrx(path: Path) -> np.ndarray:
    rgb = np.asarray(Image.open(path).convert("RGB"))
    bgrx = np.empty((*rgb.shape[:2], 4), np.uint8)
    bgrx[:, :, :3] = rgb[:, :, ::-1]
    bgrx[:, :, 3] = 255
    return bgrx


class ImageStream:
    """Same interface as PipeWireStream; cycles through images every `hold_s`."""

    def __init__(self, paths: list[Path], max_fps: float = 5, hold_s: float = 4.0) -> None:
        if not paths:
            raise ValueError("no images")
        self.max_fps = max_fps
        self.hold_s = hold_s
        self.source_frames = 0
        self.kept_frames = 0
        self._images = [load_bgrx(p) for p in paths]
        self._t0 = time.monotonic()

    def start(self, wait_s: float = 0) -> None:
        self._t0 = time.monotonic()

    def latest(self) -> tuple[int, float, np.ndarray | None]:
        elapsed = time.monotonic() - self._t0
        frame_id = int(elapsed * self.max_fps) + 1
        self.source_frames = self.kept_frames = frame_id
        image = self._images[int(elapsed / self.hold_s) % len(self._images)]
        return frame_id, self._t0 + frame_id / self.max_fps, image

    def poll_error(self) -> str | None:
        return None

    def stop(self) -> None:
        pass
