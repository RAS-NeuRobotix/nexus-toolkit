"""Thread-safe log helpers for PyQt6 dialogs."""

from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QTextEdit

from nexus_toolkit.ui.design_system import MAX_LOG_LINES


class LogBridge(QObject):
    """Emit log lines from any thread; connect to a main-thread slot."""

    line = pyqtSignal(str)


def append_log_limited(log_view: QTextEdit, line: str, max_lines: int = MAX_LOG_LINES) -> None:
    log_view.append(line)
    document = log_view.document()
    overflow = document.blockCount() - max_lines
    if overflow <= 0:
        return

    cursor = QTextCursor(document)
    cursor.movePosition(QTextCursor.MoveOperation.Start)
    cursor.movePosition(
        QTextCursor.MoveOperation.Down,
        QTextCursor.MoveMode.KeepAnchor,
        overflow,
    )
    cursor.removeSelectedText()
    cursor.deleteChar()
