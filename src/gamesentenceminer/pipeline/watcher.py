"""Decide when a region is worth reading, so OCR runs as rarely as possible."""

from __future__ import annotations

import math

import numpy as np


def signature(crop: np.ndarray, step: int = 4) -> np.ndarray:
    """Tiny grayscale thumbnail of a BGR(x) crop; cheap to compare."""
    return crop[::step, ::step, :3].mean(axis=2, dtype=np.float32)


def mean_abs_diff(a: np.ndarray, b: np.ndarray) -> float:
    if a.shape != b.shape:
        return math.inf
    return float(np.abs(a - b).mean())


class ChangeWatcher:
    """Tracks one region across frames.

    A read is due once the content differs from what was last read *and* has
    stopped changing for `settle_s` (so a typewriter animation is read once, at
    the end). Blank regions (a closed dialog box) are never read.
    """

    def __init__(self, threshold: float = 3.0, settle_s: float = 0.4,
                 min_contrast: float = 6.0) -> None:
        self.threshold = threshold
        self.settle_s = settle_s
        self.min_contrast = min_contrast
        self._prev: np.ndarray | None = None
        self._reference: np.ndarray | None = None  # signature at the last read
        self._last_change = -math.inf
        self._pending = False

    def feed(self, crop: np.ndarray, now: float) -> None:
        sig = signature(crop)
        if self._prev is None or mean_abs_diff(sig, self._prev) > self.threshold:
            self._last_change = now
        if self._reference is None or mean_abs_diff(sig, self._reference) > self.threshold:
            self._pending = True
        self._prev = sig

    def ready(self, now: float) -> bool:
        """True once per settled change; call on every tick, with or without a new frame."""
        if not self._pending or self._prev is None or now - self._last_change < self.settle_s:
            return False
        self._pending = False
        self._reference = self._prev
        return float(self._prev.std()) >= self.min_contrast

    def forget(self) -> None:
        """Make the current content count as unread (e.g. after a failed read)."""
        self._reference = None
        self._pending = self._prev is not None
