"""Background worker for Edge package update."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from nexus_toolkit.services.edge_deploy import EdgeDeployRunner


class EdgeDeployWorker(QThread):
    line = pyqtSignal(str)
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str)

    def __init__(
        self,
        runner: EdgeDeployRunner,
        host: str,
        user: str,
        password: str,
        local_tar: Path,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.runner = runner
        self.host = host
        self.user = user
        self.password = password
        self.local_tar = local_tar

    def run(self) -> None:
        ok, message = self.runner.run_blocking(
            host=self.host,
            user=self.user,
            password=self.password,
            local_tar=self.local_tar,
            on_line=self.line.emit,
            on_progress=lambda pct, label: self.progress.emit(pct, label),
        )
        self.finished.emit(ok, message)
