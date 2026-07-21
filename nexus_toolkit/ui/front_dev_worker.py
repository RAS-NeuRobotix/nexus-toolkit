"""Background worker for frontend dev server logs."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from nexus_toolkit.services.frontend_dev import FrontendDevRunner


class FrontDevWorker(QThread):
    line = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, runner: FrontendDevRunner, app_dir: Path, parent=None) -> None:
        super().__init__(parent)
        self.runner = runner
        self.app_dir = app_dir

    def run(self) -> None:
        started, message = self.runner.start(self.app_dir)
        self.line.emit(message)
        if not started:
            self.finished.emit(False, message)
            return

        process = self.runner.stdout
        if process is None:
            self.finished.emit(False, "Failed to read frontend process output")
            return

        for line in process:
            self.line.emit(line.rstrip("\n"))
            if self.isInterruptionRequested():
                self.runner.stop()
                self.finished.emit(False, "Frontend dev server stopped")
                return

        exit_code = self.runner.wait()
        if exit_code == 0:
            self.finished.emit(True, "Frontend dev server exited")
        else:
            self.finished.emit(False, f"Frontend dev server exited with code {exit_code}")
