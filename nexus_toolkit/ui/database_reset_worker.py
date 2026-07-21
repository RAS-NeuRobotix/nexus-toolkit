"""Background worker for Nexus database reset."""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from nexus_toolkit.services.database import reset_nexus_database


class DatabaseResetWorker(QThread):
    line = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, password: str | None = None, parent=None) -> None:
        super().__init__(parent)
        self.password = password

    def run(self) -> None:
        ok, message = reset_nexus_database(
            password=self.password,
            on_status=self.line.emit,
        )
        self.finished.emit(ok, message)
