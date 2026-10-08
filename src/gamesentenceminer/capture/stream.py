"""PipeWire video stream -> latest BGRx frame, rate-limited at the source."""

from __future__ import annotations

import os
import threading
import time

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstVideo", "1.0")
import numpy as np  # noqa: E402
from gi.repository import Gst, GstVideo  # noqa: E402

Gst.init(None)


class StreamError(RuntimeError):
    pass


class PipeWireStream:
    """Consumes a portal PipeWire node. Frames arrive on GStreamer's thread.

    Surplus frames are dropped at the source pad, before any conversion, and
    the compositor is asked for at most `max_fps` (Mutter honours this).
    No GLib main loop is needed: errors are polled with `poll_error()`.
    """

    def __init__(self, fd: int, node_id: int, max_fps: float,
                 negotiate_max_fps: bool = True) -> None:
        self.max_fps = max_fps
        self.source_frames = 0  # frames the compositor sent
        self.kept_frames = 0
        self._min_interval = 1.0 / max_fps
        self._last_kept = 0.0
        self._lock = threading.Lock()
        self._frame: np.ndarray | None = None
        self._frame_id = 0
        self._frame_time = 0.0

        probe = Gst.ElementFactory.make("pipewiresrc")
        if probe is None:
            raise StreamError("GStreamer pipewiresrc missing (apt install gstreamer1.0-pipewire)")
        # The portal hands out a node *id*: `path` takes an id, `target-object` a serial.
        target = "path" if probe.find_property("path") else "target-object"
        caps = f" ! video/x-raw,max-framerate={int(max_fps)}/1" if negotiate_max_fps else ""
        # pipewiresrc must be constrained to video/x-raw or negotiation fails.
        self.pipeline = Gst.parse_launch(
            f"pipewiresrc name=src fd={os.dup(fd)} {target}={node_id} do-timestamp=true"
            f"{caps} ! videoconvert ! video/x-raw,format=BGRx"
            " ! appsink name=sink emit-signals=true max-buffers=1 drop=true sync=false")
        src = self.pipeline.get_by_name("src")
        src.get_static_pad("src").add_probe(Gst.PadProbeType.BUFFER, self._on_src_buffer)
        self.pipeline.get_by_name("sink").connect("new-sample", self._on_new_sample)

    def _on_src_buffer(self, _pad, _info):
        self.source_frames += 1
        now = time.monotonic()
        if now - self._last_kept < self._min_interval:
            return Gst.PadProbeReturn.DROP
        self._last_kept = now
        return Gst.PadProbeReturn.OK

    def _on_new_sample(self, sink):
        sample = sink.emit("pull-sample")
        buf = sample.get_buffer()
        info = GstVideo.VideoInfo.new_from_caps(sample.get_caps())
        data = buf.extract_dup(0, buf.get_size())
        stride, h, w = info.stride[0], info.height, info.width
        frame = np.frombuffer(data, np.uint8, count=stride * h).reshape(h, stride)
        frame = frame[:, : w * 4].reshape(h, w, 4)
        with self._lock:
            self._frame = frame
            self._frame_id += 1
            self._frame_time = time.monotonic()
        self.kept_frames += 1
        return Gst.FlowReturn.OK

    def start(self, wait_s: float = 3.0) -> None:
        """Start and wait for the first frame or an error."""
        self.pipeline.set_state(Gst.State.PLAYING)
        deadline = time.monotonic() + wait_s
        while time.monotonic() < deadline and not self.kept_frames:
            error = self.poll_error()
            if error:
                raise StreamError(error)
            time.sleep(0.05)

    def latest(self) -> tuple[int, float, np.ndarray | None]:
        """(frame_id, monotonic time, BGRx frame). frame_id grows with each new frame."""
        with self._lock:
            return self._frame_id, self._frame_time, self._frame

    def poll_error(self) -> str | None:
        bus = self.pipeline.get_bus()
        msg = bus.pop_filtered(Gst.MessageType.ERROR | Gst.MessageType.EOS)
        if msg is None:
            return None
        if msg.type == Gst.MessageType.EOS:
            return "stream ended"
        err, _debug = msg.parse_error()
        return err.message

    def stop(self) -> None:
        self.pipeline.set_state(Gst.State.NULL)
