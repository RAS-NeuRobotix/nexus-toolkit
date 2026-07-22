#!/bin/bash
set -euo pipefail

TOOLKIT_DIR="$(cd "$(dirname "$0")" && pwd)"
ICON_SRC="$TOOLKIT_DIR/assets/nexus-toolkit.png"
CHOSEN_ICON="$HOME/.cursor/projects/home-almog-ras-nexus-back/assets/nexus-toolkit-icon-04-drone-link.png"
DESKTOP_FILE="$HOME/.local/share/applications/nexus-toolkit.desktop"
HICOLOR="$HOME/.local/share/icons/hicolor"
ICON_NAME="nexus-toolkit"

mkdir -p "$HOME/.local/share/applications" "$TOOLKIT_DIR/assets"

# Materialize chosen Drone Link icon into toolkit assets.
(cd "$TOOLKIT_DIR" && PYTHONPATH="$TOOLKIT_DIR${PYTHONPATH:+:$PYTHONPATH}" python3 -c \
  "from nexus_toolkit.app_icon import ensure_app_icon; print(ensure_app_icon())") || true

if [[ ! -f "$ICON_SRC" && -f "$CHOSEN_ICON" ]]; then
  cp "$CHOSEN_ICON" "$ICON_SRC"
fi

if [[ -f "$ICON_SRC" ]]; then
  # Theme icon name (not absolute path) — required for GNOME app grid / dock.
  for size in 16 24 32 48 64 128 256 512; do
    dir="$HICOLOR/${size}x${size}/apps"
    mkdir -p "$dir"
    # Prefer a properly resized copy when Pillow is available.
    python3 - "$ICON_SRC" "$dir/$ICON_NAME.png" "$size" <<'PY' 2>/dev/null || cp "$ICON_SRC" "$dir/$ICON_NAME.png"
import sys
from pathlib import Path
src, dest, size = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])
try:
    from PIL import Image
    im = Image.open(src).convert("RGBA")
    im = im.resize((size, size), Image.Resampling.LANCZOS)
    im.save(dest, format="PNG")
except Exception:
    import shutil
    shutil.copy2(src, dest)
PY
  done
  mkdir -p "$HOME/.local/share/icons"
  cp "$ICON_SRC" "$HOME/.local/share/icons/$ICON_NAME.png"
  ICON_VALUE="$ICON_NAME"
else
  ICON_VALUE="utilities-terminal"
fi

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Version=1.0
Name=Nexus Toolkit
Comment=Jira and Nexus Control for Ubuntu
Exec=python3 $TOOLKIT_DIR/main.py
Path=$TOOLKIT_DIR
Icon=$ICON_VALUE
Terminal=false
Type=Application
Categories=Development;Utility;
StartupNotify=true
StartupWMClass=nexus-toolkit
EOF

chmod +x "$DESKTOP_FILE"

# Refresh caches so GNOME picks up the new icon immediately.
touch "$HICOLOR"
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -f -t "$HICOLOR" >/dev/null 2>&1 || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true
fi
if command -v xdg-desktop-menu >/dev/null 2>&1; then
  xdg-desktop-menu forceupdate >/dev/null 2>&1 || true
fi

echo "Installed: $DESKTOP_FILE"
echo "Icon name: $ICON_VALUE"
echo "Icon files under: $HICOLOR/*/apps/$ICON_NAME.png"
echo "Tip: if the dock still shows a generic icon, fully quit the app and launch it from Activities → Nexus Toolkit (not python3 main.py)."
