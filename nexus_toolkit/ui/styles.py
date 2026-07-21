"""Application-wide Qt styles — Nexus tactical palette."""

from nexus_toolkit.ui.design_system import (
    COLOR_BACKGROUND,
    COLOR_BORDER,
    COLOR_BORDER_SUBTLE,
    COLOR_ERROR,
    COLOR_FOCUS,
    COLOR_HEADER,
    COLOR_MUTED,
    COLOR_PRIMARY,
    COLOR_PRIMARY_HOVER,
    COLOR_STRONG_BLUE,
    COLOR_SUCCESS,
    COLOR_SURFACE,
    COLOR_SURFACE_ALT,
    COLOR_TEXT,
    COLOR_TEXT_SOFT,
    COLOR_WARNING,
)

APP_STYLESHEET = f"""
QWidget {{
    background-color: {COLOR_BACKGROUND};
    color: {COLOR_TEXT};
    font-size: 13px;
}}

QDialog {{
    background-color: {COLOR_SURFACE};
    color: {COLOR_TEXT};
}}

QLabel {{
    background: transparent;
    color: {COLOR_TEXT};
}}

QLabel[class="page-title"] {{
    font-size: 22px;
    font-weight: bold;
    color: {COLOR_TEXT};
}}

QLabel[class="section-title"] {{
    font-size: 16px;
    font-weight: bold;
    margin-top: 8px;
    color: {COLOR_STRONG_BLUE};
}}

QLabel[class="subtitle"] {{
    color: {COLOR_TEXT_SOFT};
    margin-bottom: 16px;
}}

QLabel[class="muted"] {{
    color: {COLOR_MUTED};
    font-size: 11px;
}}

QPushButton {{
    background-color: {COLOR_SURFACE_ALT};
    color: {COLOR_TEXT};
    border: 1px solid {COLOR_BORDER};
    border-radius: 4px;
    padding: 6px 12px;
    min-height: 28px;
}}

QPushButton:hover {{
    border-color: {COLOR_FOCUS};
    background-color: {COLOR_SURFACE};
}}

QPushButton:disabled {{
    color: {COLOR_MUTED};
    background-color: {COLOR_HEADER};
    border-color: {COLOR_BORDER_SUBTLE};
}}

QPushButton[class="launcher"] {{
    font-size: 14px;
    padding: 10px 16px;
    text-align: center;
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_PRIMARY};
}}

QPushButton[class="launcher"]:hover {{
    background-color: {COLOR_SURFACE_ALT};
    border-color: {COLOR_PRIMARY_HOVER};
}}

QPushButton[class="primary"] {{
    background-color: {COLOR_PRIMARY};
    color: white;
    border: 1px solid {COLOR_PRIMARY};
    font-weight: bold;
}}

QPushButton[class="primary"]:hover {{
    background-color: {COLOR_PRIMARY_HOVER};
    border-color: {COLOR_PRIMARY_HOVER};
}}

QPushButton[class="secondary"] {{
    background-color: {COLOR_SURFACE_ALT};
    color: {COLOR_TEXT_SOFT};
    border: 1px solid {COLOR_BORDER_SUBTLE};
}}

QPushButton[class="secondary"]:hover {{
    color: {COLOR_TEXT};
    border-color: {COLOR_FOCUS};
}}

QPushButton[class="danger"] {{
    color: {COLOR_ERROR};
    border-color: {COLOR_ERROR};
    background-color: {COLOR_SURFACE_ALT};
}}

QPushButton[class="danger"]:hover {{
    background-color: {COLOR_SURFACE};
}}

QPushButton[class="compact"] {{
    padding: 4px 6px;
    min-height: 24px;
    font-size: 12px;
}}

QTextEdit, QPlainTextEdit, QTextBrowser {{
    background-color: {COLOR_SURFACE_ALT};
    color: {COLOR_TEXT};
    selection-background-color: {COLOR_STRONG_BLUE};
    selection-color: white;
    border: 1px solid {COLOR_BORDER};
    border-radius: 3px;
    padding: 6px;
}}

QLineEdit {{
    background-color: {COLOR_SURFACE_ALT};
    color: {COLOR_TEXT};
    selection-background-color: {COLOR_STRONG_BLUE};
    selection-color: white;
    border: 1px solid {COLOR_BORDER};
    border-radius: 3px;
    padding: 4px 6px;
}}

QTextEdit:focus, QPlainTextEdit:focus, QLineEdit:focus, QTextBrowser:focus {{
    border: 1px solid {COLOR_FOCUS};
}}

QTableWidget {{
    background-color: {COLOR_SURFACE_ALT};
    alternate-background-color: {COLOR_SURFACE};
    color: {COLOR_TEXT};
    gridline-color: {COLOR_BORDER};
    border: 1px solid {COLOR_BORDER};
    border-radius: 3px;
}}

QHeaderView::section {{
    background-color: {COLOR_HEADER};
    color: {COLOR_TEXT_SOFT};
    padding: 6px 8px;
    border: none;
    border-right: 1px solid {COLOR_BORDER};
    border-bottom: 1px solid {COLOR_BORDER};
    font-weight: bold;
}}

QTableWidget::item:selected {{
    background-color: {COLOR_PRIMARY};
    color: white;
}}

QToolButton[class="password-toggle"] {{
    background: transparent;
    border: 1px solid {COLOR_BORDER};
    border-radius: 3px;
    color: {COLOR_TEXT_SOFT};
    min-width: 32px;
    max-width: 36px;
    min-height: 28px;
    padding: 2px;
    font-size: 14px;
}}

QToolButton[class="password-toggle"]:hover {{
    background: {COLOR_SURFACE};
    color: {COLOR_TEXT};
    border-color: {COLOR_FOCUS};
}}

QToolButton[class="password-toggle"]:checked {{
    background: {COLOR_SURFACE};
    color: {COLOR_STRONG_BLUE};
}}

QDialogButtonBox QPushButton {{
    min-width: 80px;
    min-height: 28px;
    padding: 4px 12px;
}}

QTabWidget::pane {{
    border: 1px solid {COLOR_BORDER};
    border-radius: 3px;
    top: -1px;
    background: {COLOR_SURFACE};
}}

QTabBar::tab {{
    background: {COLOR_HEADER};
    color: {COLOR_TEXT_SOFT};
    border: 1px solid {COLOR_BORDER};
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    padding: 8px 18px;
    margin-right: 2px;
    min-width: 90px;
}}

QTabBar::tab:selected {{
    background: {COLOR_SURFACE};
    color: {COLOR_TEXT};
    border-color: {COLOR_FOCUS};
}}

QTabBar::tab:hover:!selected {{
    color: {COLOR_TEXT};
    background: {COLOR_SURFACE_ALT};
}}

QProgressBar {{
    background-color: {COLOR_SURFACE_ALT};
    border: 1px solid {COLOR_BORDER};
    border-radius: 3px;
    color: {COLOR_TEXT};
    text-align: center;
    min-height: 20px;
    max-height: 22px;
}}

QProgressBar::chunk {{
    background-color: {COLOR_PRIMARY};
    border-radius: 2px;
}}

QCheckBox {{
    spacing: 6px;
    color: {COLOR_TEXT};
    background: transparent;
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {COLOR_BORDER_SUBTLE};
    border-radius: 3px;
    background: {COLOR_SURFACE_ALT};
}}

QCheckBox::indicator:checked {{
    background: {COLOR_PRIMARY};
    border-color: {COLOR_PRIMARY};
}}

QScrollBar:vertical {{
    background: {COLOR_SURFACE};
    width: 10px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background: {COLOR_BORDER_SUBTLE};
    border-radius: 4px;
    min-height: 24px;
}}

QScrollBar::handle:vertical:hover {{
    background: {COLOR_MUTED};
}}
"""

STATUS_OK = COLOR_SUCCESS
STATUS_ERROR = COLOR_ERROR
STATUS_WARNING = COLOR_WARNING
