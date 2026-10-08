#!/usr/bin/env bash
# Install system packages and the Python environment (Ubuntu 24.04 / 26.04, GNOME).
set -euo pipefail
cd "$(dirname "$0")/.."

APT_PACKAGES=(
  # Screen capture: portal PipeWire stream read through GStreamer
  gstreamer1.0-pipewire gstreamer1.0-plugins-base gstreamer1.0-tools
  gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0
  # Building PyGObject inside the virtualenv
  build-essential pkg-config libgirepository-2.0-dev libcairo2-dev
  # Qt's X11 platform plugin, used for the overlay through XWayland
  libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-keysyms1 libxcb-xkb1
)

echo "==> System packages (needs sudo)"
sudo apt-get update
sudo apt-get install -y "${APT_PACKAGES[@]}"

if ! command -v uv >/dev/null 2>&1; then
  echo "==> Installing uv (Python package manager, https://docs.astral.sh/uv/)"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
else
  # Old uv releases can't read newer lock files; update when uv manages itself.
  uv self update >/dev/null 2>&1 || echo "note: could not self-update uv ($(uv --version));" \
    "if 'uv sync' fails, update uv the way you installed it"
fi

echo "==> Python environment (first run builds PyGObject, takes a minute)"
uv sync

echo
echo "Done. Next steps: docs/FAZ0.md"
