#!/usr/bin/env python3
"""Phase 0: report the desktop facts the capture/overlay design depends on.

Standard library only, so it runs with the system python3 before any setup:

    python3 tools/spikes/check_env.py
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys

PORTAL_ARGS = [
    "gdbus", "call", "--session",
    "--dest", "org.freedesktop.portal.Desktop",
    "--object-path", "/org/freedesktop/portal/desktop",
    "--method", "org.freedesktop.DBus.Properties.Get",
]


def run(cmd: list[str], timeout: float = 5.0) -> str | None:
    """Return stripped stdout of a successful command, else None."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def portal_prop(interface: str, prop: str) -> str | None:
    out = run([*PORTAL_ARGS, f"org.freedesktop.portal.{interface}", prop])
    if out is None:
        return None
    # gdbus prints e.g. "(<uint32 5>,)"
    match = re.search(r"<(?:uint32 )?(.*)>", out)
    return match.group(1) if match else out


def deb_version(package: str) -> str | None:
    out = run(["dpkg-query", "-W", "-f=${Status}|${Version}", package])
    if not out or "install ok installed" not in out:
        return None
    return out.split("|", 1)[1]


def os_name() -> str:
    try:
        with open("/etc/os-release", encoding="utf-8") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return platform.platform()


def gpu() -> str:
    out = run(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"])
    if out:
        name, _, driver = out.partition(",")
        return f"{name.strip()} (NVIDIA driver {driver.strip()})"
    out = run(["lspci"])
    if out:
        vga = [ln.split(": ", 1)[-1] for ln in out.splitlines() if re.search(r"VGA|3D", ln)]
        if vga:
            return "; ".join(vga)
    return "unknown"


def displays() -> str:
    # Through XWayland on a Wayland session; good enough for resolution/refresh.
    out = run(["xrandr", "--current"])
    if not out:
        return "unknown (xrandr unavailable)"
    modes = []
    for line in out.splitlines():
        if "*" in line:
            parts = line.split()
            rates = [p for p in parts[1:] if "*" in p]
            modes.append(f"{parts[0]} @ {rates[0].rstrip('*+')} Hz" if rates else parts[0])
    return ", ".join(modes) or "unknown"


def describe_bits(value: str | None, names: dict[int, str]) -> str:
    if value is None:
        return "-"
    try:
        bits = int(value)
    except ValueError:
        return value
    return f"{bits} ({', '.join(n for b, n in names.items() if bits & b) or 'none'})"


def main() -> int:
    session = os.environ.get("XDG_SESSION_TYPE", "?")
    sc_version = portal_prop("ScreenCast", "version")
    gs_version = portal_prop("GlobalShortcuts", "version")
    pipewiresrc = (
        run(["gst-inspect-1.0", "pipewiresrc"]) is not None
        if shutil.which("gst-inspect-1.0")
        else deb_version("gstreamer1.0-pipewire") is not None
    )
    pipewire = run(["pipewire", "--version"])

    rows = [
        ("OS", os_name()),
        ("Kernel", platform.release()),
        ("Session type", session),
        ("Desktop", os.environ.get("XDG_CURRENT_DESKTOP", "?")),
        ("WAYLAND_DISPLAY / DISPLAY",
         f"{os.environ.get('WAYLAND_DISPLAY', '-')} / {os.environ.get('DISPLAY', '-')}"),
        ("GNOME Shell", run(["gnome-shell", "--version"]) or "not found"),
        ("GPU", gpu()),
        ("Displays", displays()),
        ("PipeWire", pipewire.splitlines()[-1] if pipewire else "not found"),
        ("xdg-desktop-portal", deb_version("xdg-desktop-portal") or "not installed"),
        ("xdg-desktop-portal-gnome", deb_version("xdg-desktop-portal-gnome") or "not installed"),
        ("Portal ScreenCast version", sc_version or "unavailable"),
        ("  source types", describe_bits(portal_prop("ScreenCast", "AvailableSourceTypes"),
                                         {1: "monitor", 2: "window", 4: "virtual"})),
        ("  cursor modes", describe_bits(portal_prop("ScreenCast", "AvailableCursorModes"),
                                         {1: "hidden", 2: "embedded", 4: "metadata"})),
        ("Portal GlobalShortcuts version", gs_version or "unavailable"),
        ("GStreamer pipewiresrc", "yes" if pipewiresrc else "no"),
        ("Xwayland", shutil.which("Xwayland") or "not found"),
        ("libxcb-cursor0 (Qt xcb)", deb_version("libxcb-cursor0") or "not installed"),
        ("uv", run(["uv", "--version"]) or "not found"),
        ("System python3", sys.version.split()[0]),
    ]

    width = max(len(k) for k, _ in rows)
    print("== gamesentenceminer: environment check ==")
    for key, value in rows:
        print(f"{key.ljust(width)} : {value}")

    notes = []
    if session != "wayland":
        notes.append(f"Session is '{session}', not 'wayland'; the plan targets GNOME on Wayland.")
    if not sc_version:
        notes.append("ScreenCast portal not reachable: screen capture will not work.")
    if not gs_version:
        notes.append("No GlobalShortcuts portal (expected on GNOME 46 / Ubuntu 24.04): "
                     "hotkeys will go through GNOME custom shortcuts.")
    if not pipewiresrc or not shutil.which("uv") or not deb_version("libxcb-cursor0"):
        notes.append("Missing packages or uv: run scripts/setup_ubuntu.sh.")
    if notes:
        print("\nNotes:")
        for note in notes:
            print(f"- {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
