"""Design tokens and bilingual helpers for Nexus Toolkit UI.

Colors aligned with Nexus app-tactical `main.css` (@theme):
  --color-c-cobalt-blue, --color-c-blue, --color-light-green, --color-c-alert-red, etc.
"""

from __future__ import annotations

# Brand — from Nexus tactical theme
COLOR_COBALT_BLUE = "#0c53a6"       # --color-c-cobalt-blue
COLOR_BLUE = "#259dff"              # --color-c-blue
COLOR_STRONG_BLUE = "#6699ff"       # --color-c-strong-blue
COLOR_DEEP_NAVY = "#192a3c"         # --color-c-deep-navy
COLOR_DARK_BLUE = "#2c3e50"         # --color-c-dark-blue

# Semantic
COLOR_SUCCESS = "#00bf99"            # --color-light-green
COLOR_ERROR = "#fb5959"             # --color-c-alert-red
COLOR_WARNING = "#ffa500"           # --color-c-orange

# Surfaces
COLOR_BACKGROUND = "#232323"        # --color-c-bg-232323
COLOR_SURFACE = "#383838"           # --color-c-light-gray
COLOR_SURFACE_ALT = "#303030"       # settings panels in Nexus
COLOR_HEADER = "#252525"            # --color-c-black-300
COLOR_BORDER = "#4c4c4c"            # --color-c-dark-gray
COLOR_BORDER_SUBTLE = "#666666"     # --color-dark-light-gray

# Text
COLOR_TEXT = "#e8ecef"
COLOR_TEXT_SOFT = "#b2b2b2"        # --color-soft-gray
COLOR_MUTED = "#878787"             # --color-c-gray

# Aliases used across the app
COLOR_PRIMARY = COLOR_COBALT_BLUE
COLOR_PRIMARY_HOVER = COLOR_BLUE
COLOR_FOCUS = COLOR_STRONG_BLUE

SPACING_XS = 4
SPACING_SM = 8
SPACING_MD = 16
SPACING_LG = 24

LAUNCHER_BTN_WIDTH = 340
LAUNCHER_BTN_HEIGHT = 72
COMPACT_BTN_WIDTH = 56
COMPACT_BTN_WIDTH_WIDE = 76
STATUS_TABLE_ACTIONS_WIDTH = 300
STATUS_TABLE_ROW_HEIGHT = 44

DIALOG_WIDTH = 760
DIALOG_HEIGHT = 520
STATUS_DIALOG_WIDTH = 1050
STATUS_DIALOG_HEIGHT = 620

MAX_LOG_LINES = 2500


def bilingual(hebrew: str, english: str) -> str:
    return f"{hebrew}\n{english}"


def status_color(ok: bool) -> str:
    return COLOR_SUCCESS if ok else COLOR_ERROR
