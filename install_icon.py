#!/usr/bin/env python3
"""Materialize assets/nexus-toolkit.png (Drone Link) and refresh the .desktop icon."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TOOLKIT_DIR = Path(__file__).resolve().parent
if str(TOOLKIT_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLKIT_DIR))

from nexus_toolkit.app_icon import ensure_app_icon


def main() -> int:
    path = ensure_app_icon()
    print(f"Icon ready: {path}")
    script = TOOLKIT_DIR / "install-desktop.sh"
    if script.is_file():
        subprocess.run(["bash", str(script)], check=False, cwd=str(TOOLKIT_DIR))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
