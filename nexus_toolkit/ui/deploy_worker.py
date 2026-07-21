"""Background worker for system deploy."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

from nexus_toolkit.services.deploy import DeployRunner


class DeployWorker(QThread):
    line = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(
        self,
        runner: DeployRunner,
        be_version: str,
        fe_version: str,
        project: Optional[str],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.runner = runner
        self.be_version = be_version
        self.fe_version = fe_version
        self.project = project

    def run(self) -> None:
        success, message = self.runner.run_blocking(
            self.be_version,
            self.fe_version,
            self.project,
            on_line=self.line.emit,
        )
        self.finished.emit(success, message)
