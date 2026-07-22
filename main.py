#!/usr/bin/env python3
"""Nexus Ubuntu Toolkit — desktop app for Jira + Nexus operations."""

from __future__ import annotations

import sys
from pathlib import Path

_TOOLKIT_DIR = Path(__file__).resolve().parent
_VENDOR_DIR = _TOOLKIT_DIR / "vendor"
if _VENDOR_DIR.is_dir():
    vendor_path = str(_VENDOR_DIR)
    if vendor_path not in sys.path:
        sys.path.insert(0, vendor_path)

_REQUIRED_PACKAGES = (
    ("PyQt6", "PyQt6"),
    ("cursor_sdk", "cursor-sdk"),
    ("yaml", "PyYAML"),
    ("paramiko", "paramiko"),
)


def _ensure_dependencies() -> None:
    missing: list[str] = []
    for module, package in _REQUIRED_PACKAGES:
        try:
            __import__(module)
        except ImportError:
            missing.append(package)

    if not missing:
        return

    print("Missing Python packages:", ", ".join(missing))
    print()
    print("Install into the local vendor folder (no venv needed):")
    print(f"  cd {_TOOLKIT_DIR}")
    print("  python3 -m pip install -r requirements.txt --target vendor")
    print("  python3 main.py")
    sys.exit(1)


_ensure_dependencies()

from nexus_toolkit.services.cursor_sdk_patch import apply_cursor_sdk_patches

apply_cursor_sdk_patches()

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from nexus_toolkit.app import MainWindow
from nexus_toolkit.app_icon import ensure_app_icon
from nexus_toolkit.ui.styles import APP_STYLESHEET


def main() -> int:
    # Must match StartupWMClass / desktop file name so GNOME dock uses our icon.
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("nexus-toolkit")
    app.setApplicationDisplayName("Nexus Toolkit")
    app.setOrganizationName("Neurobotix")
    app.setDesktopFileName("nexus-toolkit")
    app.setStyleSheet(APP_STYLESHEET)
    icon_path = ensure_app_icon()
    icon = QIcon(str(icon_path))
    app.setWindowIcon(icon)
    window = MainWindow()
    window.setWindowIcon(icon)
    window.setWindowTitle("Nexus Toolkit")
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
