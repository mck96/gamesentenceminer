"""Client for xdg-desktop-portal's ScreenCast interface (the path OBS uses on Wayland)."""

from __future__ import annotations

import os

from gi.repository import Gio, GLib

from gamesentenceminer.paths import state_dir

PORTAL_BUS = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
SCREENCAST_IFACE = "org.freedesktop.portal.ScreenCast"
REQUEST_IFACE = "org.freedesktop.portal.Request"
SESSION_IFACE = "org.freedesktop.portal.Session"

SOURCE_MONITOR = 1
SOURCE_WINDOW = 2
SOURCE_TYPES = {"monitor": SOURCE_MONITOR, "window": SOURCE_WINDOW}
CURSOR_HIDDEN = 1
PERSIST_UNTIL_REVOKED = 2
RESPONSE_TEXT = {1: "cancelled", 2: "failed"}


class PortalError(RuntimeError):
    pass


class PortalCancelled(PortalError):
    pass


class TokenStore:
    """The portal's restore token: lets later sessions skip the share dialog.

    One per source kind, since a remembered monitor can't restore a window.
    """

    def __init__(self, source: str = "monitor") -> None:
        suffix = "" if source == "monitor" else f"_{source}"
        self.path = state_dir() / f"screencast_restore_token{suffix}"

    def load(self) -> str | None:
        try:
            return self.path.read_text().strip() or None
        except OSError:
            return None

    def save(self, token: str | None) -> None:
        if not token:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(token)

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)


class ScreenCastPortal:
    """Screen cast session (one monitor or window). Requests run a GLib loop on `context`.

    Pass a private context (pushed as thread-default) to run the handshake in a
    worker thread, so the share dialog doesn't freeze the UI.
    """

    def __init__(self, context: GLib.MainContext | None = None) -> None:
        self._ctx = context or GLib.MainContext.default()
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except GLib.Error as e:
            raise PortalError(f"no D-Bus session bus: {e.message}") from e
        self._sender = self._bus.get_unique_name()[1:].replace(".", "_")
        self._counter = 0
        self.session_handle: str | None = None

    def _token(self) -> str:
        self._counter += 1
        return f"gsm_{os.getpid()}_{self._counter}"

    def get_property(self, name: str):
        try:
            reply = self._bus.call_sync(
                PORTAL_BUS, PORTAL_PATH, "org.freedesktop.DBus.Properties", "Get",
                GLib.Variant("(ss)", (SCREENCAST_IFACE, name)), GLib.VariantType("(v)"),
                Gio.DBusCallFlags.NONE, 5000, None)
        except GLib.Error as e:
            raise PortalError(f"ScreenCast portal unavailable: {e.message}") from e
        return reply.unpack()[0]

    def _request(self, method: str, signature: str, args: tuple, options: dict,
                 timeout_s: int = 300) -> dict:
        """Call a portal method that answers through a Request::Response signal."""
        token = self._token()
        path = f"/org/freedesktop/portal/desktop/request/{self._sender}/{token}"
        loop = GLib.MainLoop.new(self._ctx, False)
        outcome: dict = {}

        def on_response(_conn, _sender, _path, _iface, _signal, params):
            outcome["code"], outcome["results"] = params.unpack()
            loop.quit()

        def on_timeout(*_):
            outcome["timeout"] = True
            loop.quit()
            return GLib.SOURCE_REMOVE

        # Subscribe before calling so the response can't slip past us. The
        # callback is dispatched on the thread-default context at this point.
        sub = self._bus.signal_subscribe(None, REQUEST_IFACE, "Response", path, None,
                                         Gio.DBusSignalFlags.NONE, on_response)
        timer = GLib.timeout_source_new_seconds(timeout_s)
        timer.set_callback(on_timeout)
        timer.attach(self._ctx)
        try:
            opts = dict(options)
            opts["handle_token"] = GLib.Variant("s", token)
            self._bus.call_sync(PORTAL_BUS, PORTAL_PATH, SCREENCAST_IFACE, method,
                                GLib.Variant(signature, (*args, opts)), GLib.VariantType("(o)"),
                                Gio.DBusCallFlags.NONE, -1, None)
            loop.run()
        except GLib.Error as e:
            raise PortalError(f"{method}: {e.message}") from e
        finally:
            self._bus.signal_unsubscribe(sub)
            timer.destroy()

        if "timeout" in outcome:
            raise PortalError(f"{method}: no answer within {timeout_s}s")
        if outcome["code"] == 1:
            raise PortalCancelled("screen sharing was cancelled")
        if outcome["code"] != 0:
            raise PortalError(f"{method}: {RESPONSE_TEXT.get(outcome['code'], outcome['code'])}")
        return outcome["results"]

    def start(self, restore_token: str | None,
              source_type: int = SOURCE_MONITOR) -> tuple[list, str | None]:
        """Returns ([(node_id, props), ...], new_restore_token)."""
        version = self.get_property("version")
        cursor_modes = self.get_property("AvailableCursorModes")

        results = self._request("CreateSession", "(a{sv})", (),
                                {"session_handle_token": GLib.Variant("s", self._token())})
        self.session_handle = results["session_handle"]

        opts = {"types": GLib.Variant("u", source_type),
                "multiple": GLib.Variant("b", False)}
        if cursor_modes & CURSOR_HIDDEN:
            # The mouse pointer over a text box would only confuse OCR.
            opts["cursor_mode"] = GLib.Variant("u", CURSOR_HIDDEN)
        if version >= 4:
            opts["persist_mode"] = GLib.Variant("u", PERSIST_UNTIL_REVOKED)
            if restore_token:
                opts["restore_token"] = GLib.Variant("s", restore_token)
        self._request("SelectSources", "(oa{sv})", (self.session_handle,), opts)

        results = self._request("Start", "(osa{sv})", (self.session_handle, ""), {})
        return results.get("streams", []), results.get("restore_token")

    def open_pipewire_remote(self) -> int:
        reply, fd_list = self._bus.call_with_unix_fd_list_sync(
            PORTAL_BUS, PORTAL_PATH, SCREENCAST_IFACE, "OpenPipeWireRemote",
            GLib.Variant("(oa{sv})", (self.session_handle, {})), GLib.VariantType("(h)"),
            Gio.DBusCallFlags.NONE, -1, None, None)
        (index,) = reply.unpack()
        return fd_list.get(index)

    def close(self) -> None:
        if not self.session_handle:
            return
        try:
            self._bus.call_sync(PORTAL_BUS, self.session_handle, SESSION_IFACE, "Close",
                                None, None, Gio.DBusCallFlags.NONE, 2000, None)
        except GLib.Error:
            pass
        self.session_handle = None
