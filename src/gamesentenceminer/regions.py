"""Text regions drawn on the source, and the app settings that go with them."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

MODES = ("auto", "manual")


@dataclass
class Region:
    """A rectangle on the captured source, stored as fractions of its size."""

    name: str
    rect: tuple[float, float, float, float]  # x, y, width, height in 0..1
    mode: str = "auto"  # auto: watched and read when it changes; manual: read on demand

    def pixel_box(self, width: int, height: int) -> tuple[int, int, int, int]:
        """(x0, y0, x1, y1) in pixels, clipped to the frame; may be empty."""
        x, y, w, h = self.rect
        x0 = min(max(int(round(x * width)), 0), width)
        y0 = min(max(int(round(y * height)), 0), height)
        x1 = min(max(int(round((x + w) * width)), x0), width)
        y1 = min(max(int(round((y + h) * height)), y0), height)
        return x0, y0, x1, y1


SOURCES = ("window", "monitor")


def _parse_regions(items) -> list[Region]:
    regions = []
    for r in items if isinstance(items, list) else []:
        try:
            rect = tuple(float(v) for v in r["rect"])
            if len(rect) == 4:
                mode = r.get("mode", "auto")
                regions.append(Region(str(r["name"]), rect, mode if mode in MODES else "auto"))
        except (KeyError, TypeError, ValueError):
            continue
    return regions


@dataclass
class Settings:
    source: str = "window"  # window: just the game; monitor: the whole screen
    target_lang: str = "tr"
    auto_read: bool = True
    overlay: bool = False
    overlay_position: str = "top"  # top | bottom
    overlay_original: bool = True
    freeze_on_return: bool = True
    max_fps: int = 5
    # Region coordinates are relative to the source, so each source keeps its own.
    window_regions: list[Region] = field(default_factory=list)
    monitor_regions: list[Region] = field(default_factory=list)

    @property
    def regions(self) -> list[Region]:
        """The regions of the current source (a live list: mutate it in place)."""
        return self.window_regions if self.source == "window" else self.monitor_regions

    @classmethod
    def load(cls, path: Path) -> Settings:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        if not isinstance(data, dict):
            return cls()
        window_regions = _parse_regions(data.pop("window_regions", []))
        # Before window capture existed, "regions" held whole-screen regions.
        monitor_regions = _parse_regions(data.pop("monitor_regions", data.pop("regions", [])))
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        try:
            settings = cls(**known)
        except TypeError:
            settings = cls()
        if settings.source not in SOURCES:
            settings.source = "window"
        settings.window_regions = window_regions
        settings.monitor_regions = monitor_regions
        return settings

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)


def next_region_name(regions: list[Region]) -> str:
    taken = {r.name for r in regions}
    i = len(regions) + 1
    while f"bölge {i}" in taken:
        i += 1
    return f"bölge {i}"
