"""Background worker for docker container actions."""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from nexus_toolkit.services.container_control import ContainerAction, run_compose_action, run_compose_action_all


class ContainerActionWorker(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(
        self,
        action: ContainerAction,
        service: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.action = action

    def run(self) -> None:
        if self.service is None:
            success, message = run_compose_action_all(self.action)
        else:
            success, message = run_compose_action(self.service, self.action)
        self.finished.emit(success, message)
