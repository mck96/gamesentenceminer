"""Frames + regions -> OCR -> translation, off the UI thread."""

from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import numpy as np
from PySide6.QtCore import QObject, Signal

from gamesentenceminer.ocr.engine import OcrEngine, OcrResult
from gamesentenceminer.pipeline.textutil import guess_lang, similar
from gamesentenceminer.pipeline.watcher import ChangeWatcher
from gamesentenceminer.regions import Region
from gamesentenceminer.translate.google import GoogleTranslator, TranslateError


@dataclass(frozen=True)
class ReadLine:
    region: str
    original: str
    translation: str | None
    source_lang: str | None
    ocr_ms: float
    error: str | None = None


def _background_priority() -> None:
    # Linux nice values are per thread; ONNX Runtime's pool threads are created
    # from this thread later and inherit it, so OCR yields to the game.
    try:
        os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), 10)
    except OSError:
        pass


def crop_region(frame: np.ndarray, region: Region,
                masks: list[tuple[int, int, int, int]] = ()) -> np.ndarray | None:
    """The region's pixels (BGR) with `masks` (x0, y0, x1, y1) blacked out.

    Returns a view into `frame` unless a mask overlaps (then a copy): frames are
    never modified after capture, and copying every crop on every frame is the
    largest steady cost while nothing on screen changes.
    """
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = region.pixel_box(w, h)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    crop = frame[y0:y1, x0:x1, :3]
    for mx0, my0, mx1, my1 in masks:
        ix0, iy0 = max(mx0, x0), max(my0, y0)
        ix1, iy1 = min(mx1, x1), min(my1, y1)
        if ix0 < ix1 and iy0 < iy1:
            if crop.base is not None:
                crop = crop.copy()
            crop[iy0 - y0:iy1 - y0, ix0 - x0:ix1 - x0] = 0
    return crop


class TextReader(QObject):
    """Owns the watchers and worker threads. Use from the UI thread only."""

    line_ready = Signal(object)  # ReadLine
    _ocr_done = Signal(str, object, object, bool)  # region, OcrResult | None, error, forced
    _translated = Signal(object)  # ReadLine

    def __init__(self, target_lang: str = "tr", parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.target_lang = target_lang
        self.ocr = OcrEngine()
        self.translator = GoogleTranslator()
        self._ocr_pool = ThreadPoolExecutor(1, "ocr", initializer=_background_priority)
        self._net_pool = ThreadPoolExecutor(2, "translate")
        self._watchers: dict[str, ChangeWatcher] = {}
        self._last_crop: dict[str, np.ndarray] = {}
        self._busy: set[str] = set()
        self._last_text: dict[str, str] = {}
        self.last_ocr_ms = 0.0
        self._ocr_done.connect(self._on_ocr_done)
        self._translated.connect(self.line_ready)

    # -- feeding ---------------------------------------------------------------

    def observe(self, frame: np.ndarray | None, now: float, regions: list[Region],
                masks: list[tuple[int, int, int, int]] = ()) -> None:
        """Call on every tick; `frame` is None when no new frame arrived."""
        names = {r.name for r in regions if r.mode == "auto"}
        for stale in set(self._watchers) - names:
            del self._watchers[stale]
            self._last_crop.pop(stale, None)
        for region in regions:
            if region.mode != "auto":
                continue
            watcher = self._watchers.setdefault(region.name, ChangeWatcher())
            if frame is not None:
                crop = crop_region(frame, region, masks)
                if crop is None:
                    continue
                watcher.feed(crop, now)
                # Static screens stop producing frames, so a change can settle
                # between frames: keep the latest crop to read then.
                self._last_crop[region.name] = crop
            if region.name in self._busy or not watcher.ready(now):
                continue
            crop = self._last_crop.get(region.name)
            if crop is not None:
                self._submit(region.name, crop, forced=False)

    def read_now(self, frame: np.ndarray, regions: list[Region],
                 masks: list[tuple[int, int, int, int]] = ()) -> int:
        """Read every region of `frame` immediately. Returns how many were queued."""
        queued = 0
        for region in regions:
            crop = crop_region(frame, region, masks)
            if crop is not None and region.name not in self._busy:
                self._submit(region.name, crop, forced=True)
                queued += 1
        return queued

    def warm_up(self) -> None:
        """Load the OCR model in the background so the first read isn't slow."""
        self._ocr_pool.submit(self.ocr.recognize, np.zeros((64, 256, 3), np.uint8))

    def forget(self, region_name: str) -> None:
        self._watchers.pop(region_name, None)
        self._last_crop.pop(region_name, None)
        self._last_text.pop(region_name, None)

    # -- workers ---------------------------------------------------------------

    def _submit(self, name: str, crop: np.ndarray, forced: bool) -> None:
        self._busy.add(name)

        def job():
            try:
                result, error = self.ocr.recognize(crop), None
            except Exception as e:  # noqa: BLE001 - report any OCR failure in the UI
                result, error = None, f"OCR: {e}"
            self._ocr_done.emit(name, result, error, forced)

        self._ocr_pool.submit(job)

    def _on_ocr_done(self, name: str, result: OcrResult | None, error: str | None,
                     forced: bool) -> None:
        self._busy.discard(name)
        if result is None:
            if name in self._watchers:
                self._watchers[name].forget()
            self.line_ready.emit(ReadLine(name, "", None, None, 0.0, error))
            return
        self.last_ocr_ms = result.elapsed_ms
        text = result.text
        if not text:
            return
        if not forced and similar(text, self._last_text.get(name, "")):
            return  # same line as before, misread a little differently
        self._last_text[name] = text
        target = self.target_lang

        def job():
            try:
                tr = self.translator.translate(text, target)
                line = ReadLine(name, text, tr.text, tr.source_lang or guess_lang(text),
                                result.elapsed_ms)
            except TranslateError as e:
                line = ReadLine(name, text, None, guess_lang(text), result.elapsed_ms,
                                f"çeviri: {e}")
            self._translated.emit(line)

        self._net_pool.submit(job)

    def shutdown(self) -> None:
        self._ocr_pool.shutdown(wait=False, cancel_futures=True)
        self._net_pool.shutdown(wait=False, cancel_futures=True)
