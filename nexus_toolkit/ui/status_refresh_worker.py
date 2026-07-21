"""Background worker for system status refresh."""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from nexus_toolkit.services.azure_auth import check_azure_login
from nexus_toolkit.services.version_info import ContainerInfo, get_container_versions


class StatusRefreshWorker(QThread):
    finished = pyqtSignal(bool, str, list)

    def run(self) -> None:
        azure_ok, azure_message = check_azure_login()
        versions: list[ContainerInfo] = get_container_versions()
        self.finished.emit(azure_ok, azure_message, versions)
