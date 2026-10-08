"""Where configuration and state live (XDG base directories)."""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "gamesentenceminer"


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / APP_NAME


def state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state"
    return Path(base) / APP_NAME
