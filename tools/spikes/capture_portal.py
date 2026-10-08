#!/usr/bin/env python3
"""Phase 0 spike: capture the screen on GNOME Wayland the way OBS does.

xdg-desktop-portal ScreenCast -> PipeWire stream -> GStreamer appsink.

Answers three questions for docs/PLAN.md:
  1. Does the permission persist (restore token), so the dialog only shows once?
  2. Can we ask the compositor for a low frame rate (max-framerate), or does it
     push every game frame at us?
  3. What does the stream cost: our CPU, gnome-shell's CPU, and (by watching the
     game's FPS counter) the game?

Typical runs (see docs/FAZ0.md):
    uv run tools/spikes/capture_portal.py --duration 10              # grant permission once
    uv run tools/spikes/capture_portal.py --delay 10 --baseline 20 --duration 40
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstVideo", "1.0")
import numpy as np  # noqa: E402
from gi.repository import Gio, GLib, Gst, GstVideo  # noqa: E402
from PIL import Image  # noqa: E402

PORTAL_BUS = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
SCREENCAST_IFACE = "org.freedesktop.portal.ScreenCast"
REQUEST_IFACE = "org.freedesktop.portal.Request"
SESSION_IFACE = "org.freedesktop.portal.Session"

SOURCE_MONITOR = 1
CURSOR_HIDDEN = 1
PERSIST_UNTIL_REVOKED = 2
RESPONSE_TEXT = {1: "cancelled by user", 2: "failed"}

STATE_HOME = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
STATE_DIR = STATE_HOME / "gamesentenceminer"
TOKEN_FILE = STATE_DIR / "screencast_restore_token"

SOUNDS = ("/usr/share/sounds/freedesktop/stereo/bell.oga",
          "/usr/share/sounds/freedesktop/stereo/complete.oga")


class PortalError(RuntimeError):
    pass


# --------------------------------------------------------------------------- portal


class ScreenCastPortal:
    """Minimal client for org.freedesktop.portal.ScreenCast (monitor source)."""

    def __init__(self) -> None:
        self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
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
                 timeout_s: int = 180) -> dict:
        """Call a portal method that answers through a Request::Response signal."""
        token = self._token()
        path = f"/org/freedesktop/portal/desktop/request/{self._sender}/{token}"
        loop = GLib.MainLoop()
        outcome: dict = {}

        def on_response(_conn, _sender, _path, _iface, _signal, params):
            outcome["code"], outcome["results"] = params.unpack()
            loop.quit()

        def on_timeout():
            outcome["timeout"] = True
            loop.quit()
            return GLib.SOURCE_REMOVE

        # Subscribe before calling so the response can't slip past us.
        sub = self._bus.signal_subscribe(None, REQUEST_IFACE, "Response", path, None,
                                         Gio.DBusSignalFlags.NONE, on_response)
        timer = GLib.timeout_add_seconds(timeout_s, on_timeout)
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
            if "timeout" not in outcome:
                GLib.source_remove(timer)

        if "timeout" in outcome:
            raise PortalError(f"{method}: no answer within {timeout_s}s")
        if outcome["code"] != 0:
            reason = RESPONSE_TEXT.get(outcome["code"], f"code {outcome['code']}")
            raise PortalError(f"{method}: {reason}")
        return outcome["results"]

    def start(self, restore_token: str | None) -> tuple[list, str | None]:
        version = self.get_property("version")
        cursor_modes = self.get_property("AvailableCursorModes")

        results = self._request("CreateSession", "(a{sv})", (),
                                {"session_handle_token": GLib.Variant("s", self._token())})
        self.session_handle = results["session_handle"]

        opts = {"types": GLib.Variant("u", SOURCE_MONITOR),
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


# --------------------------------------------------------------------------- stream


@dataclass
class StreamCounters:
    source_frames: int = 0  # frames the compositor sent us
    kept_frames: int = 0    # frames that reached the appsink after rate limiting


class FrameGrabber:
    """PipeWire (or a fake test source) -> rate limiter -> BGRx numpy frames."""

    def __init__(self, max_fps: float, negotiate_max_fps: bool,
                 fd: int | None = None, node_id: int | None = None) -> None:
        self.counters = StreamCounters()
        self.error: str | None = None
        self._min_interval = 1.0 / max_fps
        self._last_kept = 0.0
        self._lock = threading.Lock()
        self._latest: np.ndarray | None = None

        caps = f" ! video/x-raw,max-framerate={int(max_fps)}/1" if negotiate_max_fps else ""
        if fd is None:
            # Development stand-in for a 60 FPS game when no portal is available.
            # SMPTE bars make a wrong channel order obvious in the saved sample.
            src = ("videotestsrc name=src is-live=true pattern=smpte"
                   " ! video/x-raw,format=BGRx,width=1280,height=720,framerate=60/1")
        else:
            # The portal hands out a node *id*; `path` takes an id (deprecated but what
            # the portal docs use), while `target-object` expects a serial or name.
            probe = Gst.ElementFactory.make("pipewiresrc")
            target = "path" if probe.find_property("path") else "target-object"
            src = f"pipewiresrc name=src fd={fd} {target}={node_id} do-timestamp=true"
        self.description = (
            f"{src}{caps} ! videoconvert ! video/x-raw,format=BGRx"
            " ! appsink name=sink emit-signals=true max-buffers=1 drop=true sync=false"
        )
        self.pipeline = Gst.parse_launch(self.description)

        # Drop surplus frames right at the source, before videoconvert touches them.
        self._src = self.pipeline.get_by_name("src")
        self._src.get_static_pad("src").add_probe(Gst.PadProbeType.BUFFER, self._on_src_buffer)
        self.pipeline.get_by_name("sink").connect("new-sample", self._on_new_sample)

        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message::error", self._on_error)

    def _on_src_buffer(self, _pad, _info):
        self.counters.source_frames += 1
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
            self._latest = frame
        self.counters.kept_frames += 1
        return Gst.FlowReturn.OK

    def _on_error(self, _bus, message):
        err, debug = message.parse_error()
        self.error = f"{err.message} ({debug})" if debug else err.message

    def latest_frame(self) -> np.ndarray | None:
        with self._lock:
            return self._latest

    def source_caps(self) -> str | None:
        caps = self._src.get_static_pad("src").get_current_caps()
        return caps.to_string() if caps else None

    def play(self) -> None:
        self.pipeline.set_state(Gst.State.PLAYING)

    def stop(self) -> None:
        self.pipeline.get_bus().remove_signal_watch()
        self.pipeline.set_state(Gst.State.NULL)


# --------------------------------------------------------------------------- measuring


def find_gnome_shell_pid() -> int | None:
    out = subprocess.run(["pgrep", "-u", str(os.getuid()), "-x", "gnome-shell"],
                         capture_output=True, text=True)
    pids = out.stdout.split()
    return int(pids[0]) if pids else None


def proc_cpu_seconds(pid: int) -> float | None:
    try:
        with open(f"/proc/{pid}/stat", encoding="ascii") as f:
            fields = f.read().rsplit(")", 1)[1].split()
    except OSError:
        return None
    # utime and stime are fields 14 and 15 of /proc/<pid>/stat.
    return (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK")


def rss_mb() -> float:
    with open("/proc/self/status", encoding="ascii") as f:
        for line in f:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024
    return 0.0


@dataclass
class PhaseResult:
    name: str
    seconds: float = 0.0
    our_cpu_pct: float = 0.0
    gnome_shell_cpu_pct: float | None = None
    source_fps: float | None = None
    kept_fps: float | None = None
    rss_mb: float = 0.0


class Meter:
    """Samples CPU time of this process and gnome-shell; percent of one core."""

    def __init__(self, shell_pid: int | None) -> None:
        self.shell_pid = shell_pid

    def snapshot(self, counters: StreamCounters | None):
        shell = proc_cpu_seconds(self.shell_pid) if self.shell_pid else None
        return (time.monotonic(), time.process_time(), shell,
                counters.source_frames if counters else 0,
                counters.kept_frames if counters else 0)

    @staticmethod
    def delta(name: str, a, b, streaming: bool) -> PhaseResult:
        wall = max(b[0] - a[0], 1e-6)
        result = PhaseResult(name=name, seconds=round(wall, 1),
                             our_cpu_pct=round((b[1] - a[1]) / wall * 100, 2),
                             rss_mb=round(rss_mb(), 1))
        if a[2] is not None and b[2] is not None:
            result.gnome_shell_cpu_pct = round((b[2] - a[2]) / wall * 100, 2)
        if streaming:
            result.source_fps = round((b[3] - a[3]) / wall, 1)
            result.kept_fps = round((b[4] - a[4]) / wall, 1)
        return result


def run_for(seconds: float, tick_s: float = 0.0, on_tick=None) -> None:
    """Run the GLib main loop for a while, calling on_tick periodically."""
    if seconds <= 0:
        return
    loop = GLib.MainLoop()
    sources = [GLib.timeout_add(int(seconds * 1000), lambda: (loop.quit(), False)[1])]
    if on_tick:
        sources.append(GLib.timeout_add(int(tick_s * 1000), lambda: (on_tick(), True)[1]))
    loop.run()
    for source in sources[1:]:
        GLib.source_remove(source)


def beep() -> None:
    player = shutil.which("pw-play") or shutil.which("paplay")
    sound = next((s for s in SOUNDS if os.path.exists(s)), None)
    if player and sound:
        subprocess.Popen([player, sound], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        print("\a", end="", flush=True)


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# --------------------------------------------------------------------------- main


@dataclass
class Report:
    session_type: str = os.environ.get("XDG_SESSION_TYPE", "?")
    fake_source: bool = False
    portal_version: int | None = None
    restore_token_used: bool = False
    restore_token_saved: bool = False
    stream_size: list | None = None
    max_fps_requested: float = 0.0
    max_fps_negotiation: str = "off"  # off | accepted | rejected
    source_caps: str | None = None
    phases: list = field(default_factory=list)
    sample_png: str | None = None
    sample_mean_brightness: float | None = None
    error: str | None = None


def start_stream(args, report: Report, fd: int | None, node_id: int | None) -> FrameGrabber:
    """Start the pipeline, retrying without max-framerate if the compositor refuses it."""
    negotiate = not args.no_max_fps and not args.fake_source
    while True:
        grabber = FrameGrabber(args.fps, negotiate,
                               fd=os.dup(fd) if fd is not None else None, node_id=node_id)
        grabber.play()
        deadline = time.monotonic() + 3.0
        while (time.monotonic() < deadline and not grabber.error
               and not grabber.counters.kept_frames):
            run_for(0.1)
        if grabber.error and negotiate:
            log(f"max-framerate negotiation rejected: {grabber.error}")
            log("retrying without it (rate limiting on our side only)")
            grabber.stop()
            report.max_fps_negotiation = "rejected"
            negotiate = False
            continue
        if negotiate:
            report.max_fps_negotiation = "accepted"
        return grabber


def save_sample(frame: np.ndarray, out_dir: Path, report: Report) -> None:
    rgb = frame[:, :, 2::-1]  # BGRx -> RGB
    path = out_dir / "capture_sample.png"
    Image.fromarray(np.ascontiguousarray(rgb)).save(path)
    report.sample_png = str(path)
    report.sample_mean_brightness = round(float(rgb.mean()), 1)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--fps", type=float, default=5, help="frames per second we keep (default 5)")
    p.add_argument("--delay", type=float, default=0,
                   help="seconds to wait first (switch to the game)")
    p.add_argument("--baseline", type=float, default=0,
                   help="seconds to measure with no stream, for comparison")
    p.add_argument("--duration", type=float, default=20, help="seconds to stream (default 20)")
    p.add_argument("--no-max-fps", action="store_true",
                   help="don't ask the compositor for a lower frame rate")
    p.add_argument("--reset-token", action="store_true", help="forget the saved permission")
    p.add_argument("--fake-source", action="store_true",
                   help="use a GStreamer test pattern instead of the portal (development)")
    p.add_argument("--out", type=Path, default=Path("spike_out"), help="output directory")
    args = p.parse_args()

    Gst.init(None)
    args.out.mkdir(parents=True, exist_ok=True)
    report = Report(fake_source=args.fake_source, max_fps_requested=args.fps)
    meter = Meter(None if args.fake_source else find_gnome_shell_pid())
    portal: ScreenCastPortal | None = None
    grabber: FrameGrabber | None = None
    fd: int | None = None

    def tick(start_snap, name: str) -> None:
        r = Meter.delta(name, start_snap, meter.snapshot(grabber.counters if grabber else None),
                        streaming=grabber is not None)
        parts = [f"{name}: our_cpu={r.our_cpu_pct:.1f}%"]
        if r.gnome_shell_cpu_pct is not None:
            parts.append(f"gnome-shell_cpu={r.gnome_shell_cpu_pct:.1f}%")
        if r.source_fps is not None:
            parts.append(f"source={r.source_fps:.1f}fps kept={r.kept_fps:.1f}fps")
        parts.append(f"rss={r.rss_mb:.0f}MB")
        log("  ".join(parts))

    try:
        if args.delay > 0:
            log(f"waiting {args.delay:.0f}s: switch to the game now")
            run_for(args.delay)
            beep()

        if args.baseline > 0:
            log(f"baseline: {args.baseline:.0f}s without a stream (note the game's FPS)")
            snap = meter.snapshot(None)
            run_for(args.baseline, 5, lambda: tick(snap, "baseline"))
            report.phases.append(asdict(Meter.delta("baseline", snap, meter.snapshot(None), False)))
            beep()

        node_id = None
        if not args.fake_source:
            if args.reset_token:
                TOKEN_FILE.unlink(missing_ok=True)
            token = TOKEN_FILE.read_text().strip() if TOKEN_FILE.exists() else None
            report.restore_token_used = bool(token)
            portal = ScreenCastPortal()
            report.portal_version = portal.get_property("version")
            log("starting screen cast" + ("" if token else
                " (first run: pick your monitor in the GNOME dialog)"))
            streams, new_token = portal.start(token)
            if new_token:
                STATE_DIR.mkdir(parents=True, exist_ok=True)
                TOKEN_FILE.write_text(new_token)
                report.restore_token_saved = True
            if not streams:
                raise PortalError("portal returned no streams")
            node_id, props = streams[0]
            report.stream_size = list(props.get("size", ())) or None
            fd = portal.open_pipewire_remote()
            log(f"PipeWire node {node_id}, size {report.stream_size}")

        grabber = start_stream(args, report, fd, node_id)
        if grabber.error:
            raise PortalError(f"pipeline error: {grabber.error}")
        report.source_caps = grabber.source_caps()
        log(f"streaming {args.duration:.0f}s at <= {args.fps:g} fps kept"
            f" (max-framerate negotiation: {report.max_fps_negotiation})")
        snap = meter.snapshot(grabber.counters)
        run_for(args.duration, 5, lambda: tick(snap, "stream"))
        report.phases.append(
            asdict(Meter.delta("stream", snap, meter.snapshot(grabber.counters), True)))
        beep()
        if grabber.error:
            report.error = grabber.error

        frame = grabber.latest_frame()
        if frame is None:
            report.error = report.error or "no frames received"
        else:
            save_sample(frame, args.out, report)
    except (PortalError, GLib.Error) as e:
        report.error = str(e)
    except KeyboardInterrupt:
        report.error = "interrupted"
    finally:
        if grabber:
            grabber.stop()
        if portal:
            portal.close()
        if fd is not None:
            os.close(fd)

    report_path = args.out / "capture_report.json"
    report_path.write_text(json.dumps(asdict(report), indent=2, ensure_ascii=False))
    print_summary(report, report_path)
    return 1 if report.error else 0


def print_summary(report: Report, report_path: Path) -> None:
    print("\n== capture spike summary ==")
    print(f"session: {report.session_type}  portal ScreenCast v{report.portal_version}")
    if not report.fake_source:
        print(f"permission: token {'reused' if report.restore_token_used else 'not present'}, "
              f"new token {'saved' if report.restore_token_saved else 'NOT returned'}")
        if not report.restore_token_saved:
            print("  hint: GNOME only remembers the choice when 'Remember this selection'"
                  " ('Bu seçimi anımsa') is ticked in the share dialog")
    print(f"stream size: {report.stream_size}  max-framerate negotiation: "
          f"{report.max_fps_negotiation}")
    print(f"source caps: {report.source_caps}")
    if report.fake_source:
        print("(fake source: our_cpu includes generating the test pattern)")
    for ph in report.phases:
        line = f"{ph['name']:>8}: {ph['seconds']}s  our_cpu={ph['our_cpu_pct']}%"
        if ph["gnome_shell_cpu_pct"] is not None:
            line += f"  gnome-shell_cpu={ph['gnome_shell_cpu_pct']}%"
        if ph["source_fps"] is not None:
            line += f"  source={ph['source_fps']}fps  kept={ph['kept_fps']}fps"
        print(line + f"  rss={ph['rss_mb']}MB")
    if report.sample_png:
        warn = "  <-- looks BLACK" if (report.sample_mean_brightness or 0) < 2 else ""
        print(f"sample: {report.sample_png}"
              f" (mean brightness {report.sample_mean_brightness}){warn}")
    if report.error:
        print(f"ERROR: {report.error}")
    print(f"report: {report_path}")


if __name__ == "__main__":
    sys.exit(main())
