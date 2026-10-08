#!/usr/bin/env python3
"""Stand-in for xdg-desktop-portal's ScreenCast interface, for testing without GNOME.

Owns org.freedesktop.portal.Desktop on the session bus, answers the
CreateSession / SelectSources / Start / OpenPipeWireRemote flow like the real
portal, and hands out a connection to the local PipeWire daemon so that
`pipewiresrc` can consume a real node (e.g. a `pipewiresink mode=provide`).

    mock_screencast_portal.py <pipewire-node-id> [--width W --height H]
"""

from __future__ import annotations

import argparse
import os
import socket
import sys

from gi.repository import Gio, GLib

BUS_NAME = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"

INTROSPECTION = """
<node>
  <interface name="org.freedesktop.portal.ScreenCast">
    <method name="CreateSession">
      <arg type="a{sv}" direction="in"/><arg type="o" direction="out"/>
    </method>
    <method name="SelectSources">
      <arg type="o" direction="in"/><arg type="a{sv}" direction="in"/>
      <arg type="o" direction="out"/>
    </method>
    <method name="Start">
      <arg type="o" direction="in"/><arg type="s" direction="in"/>
      <arg type="a{sv}" direction="in"/><arg type="o" direction="out"/>
    </method>
    <method name="OpenPipeWireRemote">
      <arg type="o" direction="in"/><arg type="a{sv}" direction="in"/>
      <arg type="h" direction="out"/>
    </method>
    <property name="AvailableSourceTypes" type="u" access="read"/>
    <property name="AvailableCursorModes" type="u" access="read"/>
    <property name="version" type="u" access="read"/>
  </interface>
  <interface name="org.freedesktop.portal.Session">
    <method name="Close"/>
  </interface>
</node>
"""
NODE = Gio.DBusNodeInfo.new_for_xml(INTROSPECTION)
SCREENCAST, SESSION = NODE.interfaces
PROPERTIES = {"AvailableSourceTypes": 1 | 2, "AvailableCursorModes": 1 | 2 | 4, "version": 5}


def log(msg: str) -> None:
    print(f"[mock-portal] {msg}", flush=True)


class MockPortal:
    def __init__(self, node_id: int, size: tuple[int, int]) -> None:
        self.node_id = node_id
        self.size = size
        self.tokens_issued = 0
        self.sessions: dict[str, int] = {}

    def on_bus_acquired(self, conn: Gio.DBusConnection, _name: str) -> None:
        conn.register_object(PORTAL_PATH, SCREENCAST, self.on_method_call, self.on_get_property)

    def on_get_property(self, _conn, _sender, _path, _iface, name):
        return GLib.Variant("u", PROPERTIES[name])

    def on_method_call(self, conn, sender, path, iface, method, params, invocation):
        args = params.unpack()
        if iface == "org.freedesktop.portal.Session":
            conn.unregister_object(self.sessions.pop(path))
            log(f"Session.Close {path}")
            invocation.return_value(None)
            return

        options = args[-1]
        log(f"{method} options={options}")
        if method == "OpenPipeWireRemote":
            runtime_dir = os.environ["XDG_RUNTIME_DIR"]
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(os.path.join(runtime_dir, "pipewire-0"))
            fd_list = Gio.UnixFDList.new()
            index = fd_list.append(sock.fileno())
            sock.close()  # the fd list holds its own duplicate
            invocation.return_value_with_unix_fd_list(GLib.Variant("(h)", (index,)), fd_list)
            return

        client = sender[1:].replace(".", "_")
        request_path = f"{PORTAL_PATH}/request/{client}/{options['handle_token']}"
        invocation.return_value(GLib.Variant("(o)", (request_path,)))

        results: dict[str, GLib.Variant] = {}
        if method == "CreateSession":
            session_path = f"{PORTAL_PATH}/session/{client}/{options['session_handle_token']}"
            self.sessions[session_path] = conn.register_object(
                session_path, SESSION, self.on_method_call, None)
            results["session_handle"] = GLib.Variant("s", session_path)
        elif method == "Start":
            self.tokens_issued += 1
            props = {"size": GLib.Variant("(ii)", self.size), "source_type": GLib.Variant("u", 1)}
            results["streams"] = GLib.Variant("a(ua{sv})", [(self.node_id, props)])
            results["restore_token"] = GLib.Variant("s", f"mock-token-{self.tokens_issued}")

        def emit_response():
            conn.emit_signal(sender, request_path, "org.freedesktop.portal.Request", "Response",
                             GLib.Variant("(ua{sv})", (0, results)))
            return GLib.SOURCE_REMOVE

        GLib.idle_add(emit_response)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("node_id", type=int)
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=720)
    args = p.parse_args()

    portal = MockPortal(args.node_id, (args.width, args.height))
    loop = GLib.MainLoop()
    Gio.bus_own_name(Gio.BusType.SESSION, BUS_NAME, Gio.BusNameOwnerFlags.NONE,
                     portal.on_bus_acquired, lambda *_: log("ready"),
                     lambda *_: (log("could not own bus name"), loop.quit()))
    loop.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
