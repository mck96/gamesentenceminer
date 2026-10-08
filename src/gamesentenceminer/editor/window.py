"""Main window: source preview, regions, read text and translations."""

from __future__ import annotations

import threading
import time
from collections import deque
from pathlib import Path

import numpy as np
from PySide6.QtCore import QEvent, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from gamesentenceminer.editor.canvas import FrameCanvas
from gamesentenceminer.overlay import Banner
from gamesentenceminer.paths import config_dir
from gamesentenceminer.pipeline.reader import ReadLine, TextReader
from gamesentenceminer.regions import Region, Settings, next_region_name

TICK_MS = 200  # matches the default 5 fps capture
PREVIEW_INACTIVE_S = 1.0  # refresh the preview at most this often while the game has focus
RETURN_LOOKBACK_S = 0.4  # on coming back, show the frame from just before the switch
LANGUAGES = [("Türkçe", "tr"), ("English", "en")]
SOURCE_CHOICES = [("Oyun penceresi", "window"), ("Tüm ekran", "monitor")]
MODE_LABELS = [("Otomatik", "auto"), ("Elle (Oku)", "manual")]
OVERLAY_CHOICES = [("Overlay kapalı", "off"), ("Overlay üstte", "top"),
                   ("Overlay altta", "bottom")]


class MainWindow(QMainWindow):
    _capture_started = Signal(object)
    _capture_failed = Signal(str)

    def __init__(self, fake_source: list[Path] | None = None, max_fps: int | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Game Sentence Miner")
        self.resize(1280, 800)
        self.settings_path = config_dir() / "settings.json"
        self.settings = Settings.load(self.settings_path)
        if max_fps:
            self.settings.max_fps = max_fps
        self.fake_source = fake_source

        self.reader = TextReader(self.settings.target_lang, self)
        self.reader.line_ready.connect(self._on_line)
        self.capture = None
        self.banner: Banner | None = None
        self._starting = False
        self._last_frame_id = -1
        self._latest: np.ndarray | None = None
        self._frozen: np.ndarray | None = None
        self._last_preview = 0.0
        self._history: deque[tuple[float, np.ndarray]] = deque(maxlen=4)
        self._cpu_mark = (time.monotonic(), time.process_time(), 0)

        self._build_ui()
        self._capture_started.connect(self._on_capture_started)
        self._capture_failed.connect(self._on_capture_failed)
        self._apply_overlay_choice()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(TICK_MS)
        self._stats_timer = QTimer(self)
        self._stats_timer.timeout.connect(self._update_stats)
        self._stats_timer.start(1000)

    # -- UI --------------------------------------------------------------------

    def _build_ui(self) -> None:
        bar = QToolBar("Araçlar", self)
        bar.setMovable(False)
        self.addToolBar(bar)

        self.source_box = QComboBox()
        for label, code in SOURCE_CHOICES:
            self.source_box.addItem(label, code)
        self.source_box.setCurrentIndex(max(0, self.source_box.findData(self.settings.source)))
        self.source_box.setToolTip("Oyun penceresi: sadece oyun yakalanır (önerilen).\n"
                                   "Tüm ekran: monitörün tamamı.")
        self.source_box.currentIndexChanged.connect(self._on_source_changed)
        bar.addWidget(self.source_box)
        self.act_capture = QAction("▶ Yakalamayı başlat", self)
        self.act_capture.triggered.connect(self._toggle_capture)
        bar.addAction(self.act_capture)
        act_reselect = QAction("Kaynağı yeniden seç", self)
        act_reselect.setToolTip("Hatırlanan seçimi unut ve GNOME'un seçim penceresini yeniden aç")
        act_reselect.triggered.connect(self._reselect_source)
        bar.addAction(act_reselect)
        bar.addSeparator()

        self.act_freeze = QAction("❄ Dondur", self, checkable=True)
        self.act_freeze.setToolTip("Önizlemeyi o anki karede durdur; bölgeleri dondurulmuş "
                                   "kare üzerinde çiz")
        self.act_freeze.toggled.connect(self._on_freeze_toggled)
        bar.addAction(self.act_freeze)
        act_delayed = QAction("⏱ 3 sn sonra dondur", self)
        act_delayed.setToolTip("Bas, 3 saniye içinde oyuna geç: o anki oyun karesi dondurulur")
        act_delayed.triggered.connect(lambda: QTimer.singleShot(3000, self._freeze_now))
        bar.addAction(act_delayed)
        bar.addSeparator()

        act_read = QAction("🔍 Oku", self)
        act_read.setToolTip("Tüm bölgeleri gösterilen karede şimdi oku ve çevir")
        act_read.triggered.connect(self._read_now)
        bar.addAction(act_read)
        self.act_auto = QAction("Otomatik oku", self, checkable=True)
        self.act_auto.setChecked(self.settings.auto_read)
        self.act_auto.setToolTip("'Otomatik' bölgeler metin değişip durunca kendiliğinden okunur")
        self.act_auto.toggled.connect(self._on_auto_toggled)
        bar.addAction(self.act_auto)
        bar.addSeparator()

        bar.addWidget(QLabel(" Çeviri: "))
        self.lang_box = QComboBox()
        for label, code in LANGUAGES:
            self.lang_box.addItem(label, code)
        self.lang_box.setCurrentIndex(max(0, self.lang_box.findData(self.settings.target_lang)))
        self.lang_box.currentIndexChanged.connect(self._on_lang_changed)
        bar.addWidget(self.lang_box)
        self.overlay_box = QComboBox()
        for label, code in OVERLAY_CHOICES:
            self.overlay_box.addItem(label, code)
        current = self.settings.overlay_position if self.settings.overlay else "off"
        self.overlay_box.setCurrentIndex(max(0, self.overlay_box.findData(current)))
        self.overlay_box.currentIndexChanged.connect(self._on_overlay_changed)
        bar.addWidget(self.overlay_box)

        options = QMenu(self)
        self.act_return = options.addAction("Uygulamaya dönünce son oyun karesini dondur")
        self.act_return.setCheckable(True)
        self.act_return.setChecked(self.settings.freeze_on_return)
        self.act_return.toggled.connect(self._on_return_toggled)
        self.act_original = options.addAction("Overlay'de orijinal metni de göster")
        self.act_original.setCheckable(True)
        self.act_original.setChecked(self.settings.overlay_original)
        self.act_original.toggled.connect(self._on_original_toggled)
        options_button = QToolButton()
        options_button.setText("⚙")
        options_button.setToolTip("Seçenekler")
        options_button.setMenu(options)
        options_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        bar.addWidget(options_button)

        self.canvas = FrameCanvas()
        self.canvas.region_drawn.connect(self._on_region_drawn)
        self.canvas.region_changed.connect(self._on_region_changed)
        self.canvas.region_selected.connect(self._on_canvas_selected)
        self.canvas.delete_requested.connect(self._delete_region)

        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(6, 6, 6, 6)
        side_layout.addWidget(QLabel("<b>Bölgeler</b>  (önizlemede sürükleyerek çiz)"))
        self.region_list = QListWidget()
        self.region_list.currentItemChanged.connect(self._on_list_selected)
        self.region_list.itemChanged.connect(self._on_list_renamed)
        side_layout.addWidget(self.region_list, 1)
        row = QHBoxLayout()
        self.mode_box = QComboBox()
        for label, code in MODE_LABELS:
            self.mode_box.addItem(label, code)
        self.mode_box.currentIndexChanged.connect(self._on_mode_changed)
        row.addWidget(self.mode_box, 1)
        delete_btn = QPushButton("Sil")
        delete_btn.clicked.connect(lambda: self._delete_region(self._selected_name()))
        row.addWidget(delete_btn)
        side_layout.addLayout(row)
        hint = QLabel("Çift tıkla: yeniden adlandır · Delete: sil · Sağ alt köşe: boyutlandır")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray")
        side_layout.addWidget(hint)

        side.setMinimumWidth(220)
        side.setMaximumWidth(360)
        top = QSplitter(Qt.Orientation.Horizontal)
        top.addWidget(self.canvas)
        top.addWidget(side)
        top.setStretchFactor(0, 1)
        top.setStretchFactor(1, 0)
        top.setSizes([1000, 280])

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(1000)
        font = QFont()
        font.setPointSize(11)
        self.log.setFont(font)
        self.log.setPlaceholderText("Okunan metinler ve çevirileri burada görünür.")

        main = QSplitter(Qt.Orientation.Vertical)
        main.addWidget(top)
        main.addWidget(self.log)
        main.setStretchFactor(0, 3)
        main.setStretchFactor(1, 1)
        main.setSizes([600, 200])
        self.setCentralWidget(main)

        self.stats_label = QLabel()
        self.statusBar().addPermanentWidget(self.stats_label)
        self._refresh_regions()

    # -- capture ---------------------------------------------------------------

    def _toggle_capture(self) -> None:
        if self.capture:
            self._stop_capture("Yakalama durduruldu.")
        elif not self._starting:
            self._start_capture()

    def _start_capture(self) -> None:
        self._starting = True
        self.reader.warm_up()  # load the OCR model while the user picks a monitor
        self.act_capture.setEnabled(False)
        source = self.settings.source
        what = "oyun penceresini" if source == "window" else "monitörünü"
        self.statusBar().showMessage(f"Yakalama başlatılıyor… (ilk seferde GNOME'un paylaşım "
                                     f"penceresinden {what} seç)")

        def worker():
            try:
                if self.fake_source:
                    from gamesentenceminer.capture import CaptureSession
                    from gamesentenceminer.capture.fake import ImageStream

                    stream = ImageStream(self.fake_source, self.settings.max_fps)
                    stream.start()
                    session = CaptureSession(stream, source=source, token_saved=True)
                else:
                    from gamesentenceminer.capture import open_capture

                    session = open_capture(source, self.settings.max_fps)
            except Exception as e:  # noqa: BLE001 - shown to the user
                self._capture_failed.emit(str(e))
            else:
                self._capture_started.emit(session)

        threading.Thread(target=worker, name="capture-start", daemon=True).start()

    def _on_capture_started(self, session) -> None:
        self._starting = False
        self.capture = session
        self._last_frame_id = -1
        self.act_capture.setEnabled(True)
        self.act_capture.setText("■ Yakalamayı durdur")
        notes = []
        if not session.token_saved:
            notes.append("GNOME seçimi kaydetmedi: paylaşım penceresinde 'Bu seçimi anımsa' "
                         "işaretliyse bir dahaki sefere sormaz.")
        if session.source == "window":
            notes.append("Oyun kapanıp açılınca GNOME pencereyi yeniden sorabilir.")
        if session.portal and not session.max_fps_negotiated:
            notes.append("GNOME düşük FPS isteğini kabul etmedi; kareler bizde düşürülüyor.")
        self.statusBar().showMessage(" ".join(["Yakalama çalışıyor.", *notes]), 15000)

    def _on_capture_failed(self, message: str) -> None:
        self._starting = False
        self.act_capture.setEnabled(True)
        self.statusBar().showMessage(f"Yakalama başlatılamadı: {message}")

    def _stop_capture(self, message: str) -> None:
        if self.capture:
            self.capture.close()
            self.capture = None
        self._latest = None
        self._history.clear()
        self.act_capture.setText("▶ Yakalamayı başlat")
        self.statusBar().showMessage(message, 10000)

    # -- per-tick work -----------------------------------------------------------

    def _tick(self) -> None:
        if not self.capture:
            return
        stream = self.capture.stream
        error = stream.poll_error()
        if error:
            self._stop_capture(f"Yakalama kesildi: {error}")
            return
        frame_id, _t, frame = stream.latest()
        now = time.monotonic()
        is_new = frame is not None and frame_id != self._last_frame_id
        if is_new:
            self._last_frame_id = frame_id
            self._latest = frame
            if not self.isActiveWindow():
                self._history.append((now, frame))

        if self.act_auto.isChecked() and self._latest is not None:
            self.reader.observe(frame if is_new else None, now, self.settings.regions,
                                self._masks(self._latest))

        if is_new and self._frozen is None and self.isVisible() and not self.isMinimized():
            if self.isActiveWindow() or now - self._last_preview >= PREVIEW_INACTIVE_S:
                self._show_frame(frame, full=False)
                self._last_preview = now

    def _show_frame(self, frame: np.ndarray, full: bool) -> None:
        # Live preview at half resolution is plenty and 4x cheaper to draw.
        scale = 1 if full or frame.shape[1] <= 1600 else 2
        shown = frame if scale == 1 else frame[::scale, ::scale]
        if self.canvas.set_frame(shown, scale):
            self._refresh_regions()

    def _masks(self, frame: np.ndarray) -> list[tuple[int, int, int, int]]:
        # Keep our own banner out of the OCR, or it would read its translation back.
        # A window capture contains only the game, so there is nothing to mask.
        if (self.banner and self.banner.isVisible() and self.capture
                and self.capture.source == "monitor"):
            return [self.banner.frame_rect(frame.shape[1], frame.shape[0])]
        return []

    # -- freezing ----------------------------------------------------------------

    def _freeze(self, frame: np.ndarray, message: str) -> None:
        self._frozen = frame
        self._show_frame(frame, full=True)
        self.act_freeze.blockSignals(True)
        self.act_freeze.setChecked(True)
        self.act_freeze.blockSignals(False)
        self.statusBar().showMessage(message, 8000)

    def _freeze_now(self) -> None:
        if self._latest is not None:
            self._freeze(self._latest,
                         "Kare donduruldu. Bölgeleri çiz; canlı için 'Dondur'u kapat.")

    def _on_freeze_toggled(self, on: bool) -> None:
        if on:
            if self._latest is None:
                self.act_freeze.setChecked(False)
                return
            self._freeze_now()
        else:
            self._frozen = None
            if self._latest is not None:
                self._show_frame(self._latest, full=False)

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() != QEvent.Type.ActivationChange:
            return
        if not self.isActiveWindow():
            self._history.clear()
            return
        if self.act_return.isChecked() and self._history and self._frozen is None:
            cutoff = time.monotonic() - RETURN_LOOKBACK_S
            older = [f for t, f in self._history if t <= cutoff]
            frame = older[-1] if older else self._history[0][1]
            self._freeze(frame, "Ayrılmadan önceki kare donduruldu. Canlı görüntü için "
                                "'Dondur'u kapat.")
        self._history.clear()

    def _on_return_toggled(self, on: bool) -> None:
        self.settings.freeze_on_return = on
        self._save()

    def _on_original_toggled(self, on: bool) -> None:
        self.settings.overlay_original = on
        if self.banner:
            self.banner.set_show_original(on)
        self._save()

    # -- source --------------------------------------------------------------------

    def _on_source_changed(self) -> None:
        self.settings.source = self.source_box.currentData()
        self._save()
        self.reader.reset()
        self._frozen = None
        self.act_freeze.setChecked(False)
        self._refresh_regions()
        if self.capture:
            self._stop_capture("Kaynak değişti.")
            self._start_capture()

    def _reselect_source(self) -> None:
        from gamesentenceminer.capture import forget_source

        forget_source(self.settings.source)
        if self.capture:
            self._stop_capture("Kaynak yeniden seçiliyor.")
        if not self._starting:
            self._start_capture()

    # -- reading -----------------------------------------------------------------

    def _read_now(self) -> None:
        frame = self._frozen if self._frozen is not None else self._latest
        if frame is None:
            self.statusBar().showMessage("Okunacak kare yok: önce yakalamayı başlat.", 5000)
            return
        if not self.settings.regions:
            self.statusBar().showMessage("Önce önizlemede bir bölge çiz.", 5000)
            return
        count = self.reader.read_now(frame, self.settings.regions, self._masks(frame))
        self.statusBar().showMessage(f"{count} bölge okunuyor…", 3000)

    def _on_line(self, line: ReadLine) -> None:
        stamp = time.strftime("%H:%M:%S")
        if line.error and not line.original:
            self.log.appendPlainText(f"[{stamp}] {line.region}: HATA {line.error}")
            return
        lang = f" ({line.source_lang})" if line.source_lang else ""
        self.log.appendPlainText(f"[{stamp}] {line.region}{lang}: {line.original}")
        if line.translation:
            self.log.appendPlainText(f"    → {line.translation}")
        elif line.error:
            self.log.appendPlainText(f"    → HATA {line.error}")
        if self.banner and line.original:
            self.banner.show_line(line.original, line.translation or "(çeviri alınamadı)")

    def _on_auto_toggled(self, on: bool) -> None:
        self.settings.auto_read = on
        self._save()

    def _on_lang_changed(self) -> None:
        self.settings.target_lang = self.lang_box.currentData()
        self.reader.target_lang = self.settings.target_lang
        self._save()

    def _on_overlay_changed(self) -> None:
        choice = self.overlay_box.currentData()
        self.settings.overlay = choice != "off"
        if choice != "off":
            self.settings.overlay_position = choice
        self._apply_overlay_choice()
        self._save()

    def _apply_overlay_choice(self) -> None:
        if not self.settings.overlay:
            if self.banner:
                self.banner.hide()
            return
        if self.banner is None:
            self.banner = Banner(self.settings.overlay_position, self.settings.overlay_original)
        self.banner.set_position(self.settings.overlay_position)

    # -- regions -----------------------------------------------------------------

    def _selected_name(self) -> str | None:
        item = self.region_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _region(self, name: str | None) -> Region | None:
        return next((r for r in self.settings.regions if r.name == name), None)

    def _refresh_regions(self, select: str | None = None) -> None:
        select = select or self._selected_name()
        self.canvas.set_regions(self.settings.regions, select)
        self.region_list.blockSignals(True)
        self.region_list.clear()
        for region in self.settings.regions:
            item = QListWidgetItem(region.name)
            item.setData(Qt.ItemDataRole.UserRole, region.name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            self.region_list.addItem(item)
            if region.name == select:
                self.region_list.setCurrentItem(item)
        self.region_list.blockSignals(False)
        self._sync_mode_box()

    def _sync_mode_box(self) -> None:
        region = self._region(self._selected_name())
        self.mode_box.setEnabled(region is not None)
        if region:
            self.mode_box.blockSignals(True)
            self.mode_box.setCurrentIndex(max(0, self.mode_box.findData(region.mode)))
            self.mode_box.blockSignals(False)

    def _on_region_drawn(self, rect: QRectF) -> None:
        name = next_region_name(self.settings.regions)
        self.settings.regions.append(Region(name, self.canvas.normalized(rect)))
        self._save()
        self._refresh_regions(select=name)

    def _on_region_changed(self, name: str, rect: QRectF) -> None:
        region = self._region(name)
        if region:
            region.rect = self.canvas.normalized(rect)
            self.reader.forget(name)
            self._save()

    def _on_canvas_selected(self, name) -> None:
        self.region_list.blockSignals(True)
        for i in range(self.region_list.count()):
            item = self.region_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == name:
                self.region_list.setCurrentItem(item)
        if name is None:
            self.region_list.setCurrentItem(None)
        self.region_list.blockSignals(False)
        self._sync_mode_box()

    def _on_list_selected(self, current, _previous) -> None:
        name = current.data(Qt.ItemDataRole.UserRole) if current else None
        self.canvas.select(name)
        self._sync_mode_box()

    def _on_list_renamed(self, item: QListWidgetItem) -> None:
        old = item.data(Qt.ItemDataRole.UserRole)
        new = item.text().strip()
        region = self._region(old)
        if region and new and new != old and self._region(new) is None:
            region.name = new
            self.reader.forget(old)
            self._save()
        # Rebuilding the list inside its own itemChanged handler is unsafe; defer it.
        name = region.name if region else None
        QTimer.singleShot(0, lambda: self._refresh_regions(select=name))

    def _on_mode_changed(self) -> None:
        region = self._region(self._selected_name())
        if region:
            region.mode = self.mode_box.currentData()
            self.reader.forget(region.name)
            self._save()

    def _delete_region(self, name: str | None) -> None:
        region = self._region(name)
        if region:
            self.settings.regions.remove(region)
            self.reader.forget(region.name)
            self._save()
            self._refresh_regions()

    # -- misc --------------------------------------------------------------------

    def _update_stats(self) -> None:
        wall, cpu, frames = self._cpu_mark
        now_wall, now_cpu = time.monotonic(), time.process_time()
        kept = self.capture.stream.kept_frames if self.capture else 0
        fps = (kept - frames) / max(now_wall - wall, 1e-6) if self.capture else 0.0
        cpu_pct = (now_cpu - cpu) / max(now_wall - wall, 1e-6) * 100
        self._cpu_mark = (now_wall, now_cpu, kept)
        ocr = f"  OCR {self.reader.last_ocr_ms:.0f} ms" if self.reader.last_ocr_ms else ""
        self.stats_label.setText(f"CPU %{cpu_pct:.1f}  {fps:.1f} kare/sn{ocr}")

    def _save(self) -> None:
        self.settings.save(self.settings_path)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._save()
        if self.capture:
            self.capture.close()
        if self.banner:
            self.banner.close()
        self.reader.shutdown()
        super().closeEvent(event)
