"""Screen capture: portal handshake + PipeWire stream, behind one session object."""

from __future__ import annotations

import os
from dataclasses import dataclass

from gi.repository import GLib

from gamesentenceminer.capture.portal import (
    SOURCE_TYPES,
    PortalCancelled,
    PortalError,
    ScreenCastPortal,
    TokenStore,
)
from gamesentenceminer.capture.stream import PipeWireStream, StreamError

__all__ = ["CaptureSession", "PortalCancelled", "PortalError", "StreamError",
           "forget_source", "open_capture"]


@dataclass
class CaptureSession:
    stream: object  # PipeWireStream or a stand-in with the same methods
    source: str = "monitor"  # monitor | window
    size: tuple[int, int] | None = None
    token_reused: bool = False
    token_saved: bool = False
    max_fps_negotiated: bool = False
    portal: ScreenCastPortal | None = None
    fd: int | None = None

    def close(self) -> None:
        self.stream.stop()
        if self.portal:
            self.portal.close()
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


def forget_source(source: str) -> None:
    """Drop the remembered choice so the next start shows GNOME's picker again."""
    TokenStore(source).clear()


def open_capture(source: str, max_fps: float) -> CaptureSession:
    """Capture a monitor or a single window ("monitor" | "window").

    Blocking (may wait for the user in GNOME's share dialog): call off the UI thread.
    """
    tokens = TokenStore(source)
    ctx = GLib.MainContext.new()
    ctx.push_thread_default()
    try:
        portal = ScreenCastPortal(ctx)
        token = tokens.load()
        streams, new_token = portal.start(token, SOURCE_TYPES[source])
    finally:
        ctx.pop_thread_default()
    tokens.save(new_token)
    if not streams:
        portal.close()
        raise PortalError("the portal returned no stream")
    node_id, props = streams[0]
    fd = portal.open_pipewire_remote()
    session = CaptureSession(stream=None, source=source,
                             size=tuple(props.get("size", ())) or None,
                             token_reused=bool(token), token_saved=bool(new_token),
                             portal=portal, fd=fd)
    for negotiate in (True, False):
        stream = PipeWireStream(fd, node_id, max_fps, negotiate_max_fps=negotiate)
        try:
            stream.start()
        except StreamError:
            stream.stop()
            if negotiate:
                continue  # compositor refused max-framerate: limit on our side only
            session.stream = stream
            session.close()
            raise
        session.stream = stream
        session.max_fps_negotiated = negotiate
        return session
    raise AssertionError("unreachable")
