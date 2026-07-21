#!/bin/bash
set -euo pipefail

TOOLKIT_DIR="$(cd "$(dirname "$0")" && pwd)"
DESKTOP_FILE="$HOME/.local/share/applications/nexus-toolkit.desktop"

mkdir -p "$HOME/.local/share/applications"

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Name=Nexus Toolkit
Comment=Jira and Nexus Control for Ubuntu
Exec=python3 $TOOLKIT_DIR/main.py
Path=$TOOLKIT_DIR
Icon=utilities-terminal
Terminal=false
Type=Application
Categories=Development;Utility;
EOF

chmod +x "$DESKTOP_FILE"
echo "Installed: $DESKTOP_FILE"
