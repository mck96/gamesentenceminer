"""OCR through RapidOCR (PP-OCRv6 multilingual models bundled with the wheel)."""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from gamesentenceminer.pipeline.textutil import join_lines

MAX_SIDE = 960  # detection cost grows with image size; dialog text stays legible at this
MIN_HEIGHT = 48  # small UI fonts read better upscaled


def fit_scale(width: int, height: int) -> float:
    """Shrink so the long side is at most MAX_SIDE, but keep at least MIN_HEIGHT."""
    if height <= 0 or width <= 0:
        return 1.0
    scale = min(1.0, MAX_SIDE / max(width, height))
    return max(scale, MIN_HEIGHT / height) if height * scale < MIN_HEIGHT else scale


@dataclass(frozen=True)
class OcrResult:
    lines: tuple[str, ...]
    text: str
    elapsed_ms: float


class OcrEngine:
    """Not thread-safe: use from one worker thread. Loads the model on first use."""

    def __init__(self, threads: int = 2, use_cuda: bool = False) -> None:
        self.threads = threads
        self.use_cuda = use_cuda
        self._engine = None

    def _load(self):
        from rapidocr import RapidOCR  # heavy import, keep it off the UI thread

        return RapidOCR(params={
            "Global.use_cls": False,  # game text is upright
            "Global.log_level": "error",  # blank regions are normal
            "EngineConfig.onnxruntime.intra_op_num_threads": self.threads,
            "EngineConfig.onnxruntime.inter_op_num_threads": 1,
            "EngineConfig.onnxruntime.use_cuda": self.use_cuda,
            # The default scales the *short* side up to 736 px, which turns a
            # 1100x140 dialog box into ~5800 px wide and takes seconds. In "max"
            # mode RapidOCR picks its own cap (960/1500/2000 by image size), so
            # recognize() also shrinks images to MAX_SIDE first.
            "Det.limit_type": "max",
            "Det.limit_side_len": MAX_SIDE,
        })

    def recognize(self, bgr: np.ndarray) -> OcrResult:
        if self._engine is None:
            self._engine = self._load()
        start = time.perf_counter()
        image = np.ascontiguousarray(bgr[:, :, :3])
        h, w = image.shape[:2]
        scale = fit_scale(w, h)
        if scale != 1.0:
            import cv2

            interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
            image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=interpolation)
        result = self._engine(image)
        lines = tuple(t for t in (result.txts or ()) if t and t.strip())
        return OcrResult(lines, join_lines(list(lines)), (time.perf_counter() - start) * 1000)
