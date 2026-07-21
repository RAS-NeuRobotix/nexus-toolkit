"""Background workers for Edge status refresh and compose actions."""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from nexus_toolkit.services.container_control import ContainerAction
from nexus_toolkit.services.edge_control import (
    EdgeContainerInfo,
    list_edge_containers,
    run_edge_compose_action,
    run_edge_compose_action_all,
    verify_edge_compose,
)
from nexus_toolkit.services.edge_ssh import test_edge_connection


class EdgeConnectWorker(QThread):
    finished = pyqtSignal(bool, str, list)

    def __init__(
        self,
        host: str,
        user: str,
        password: str,
        compose_path: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.host = host
        self.user = user
        self.password = password
        self.compose_path = compose_path

    def run(self) -> None:
        ok, message = test_edge_connection(self.host, self.user, self.password)
        if not ok:
            self.finished.emit(False, message, [])
            return
        ok, message = verify_edge_compose(
            self.host, self.user, self.password, self.compose_path
        )
        if not ok:
            self.finished.emit(False, message, [])
            return
        try:
            infos: list[EdgeContainerInfo] = list_edge_containers(
                self.host, self.user, self.password, self.compose_path
            )
            self.finished.emit(True, f"Connected to {self.user}@{self.host}", infos)
        except Exception as exc:  # noqa: BLE001
            self.finished.emit(False, str(exc), [])


class EdgeRefreshWorker(QThread):
    finished = pyqtSignal(bool, str, list)

    def __init__(
        self,
        host: str,
        user: str,
        password: str,
        compose_path: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.host = host
        self.user = user
        self.password = password
        self.compose_path = compose_path

    def run(self) -> None:
        try:
            infos = list_edge_containers(
                self.host, self.user, self.password, self.compose_path
            )
            self.finished.emit(True, "Edge status refreshed", infos)
        except Exception as exc:  # noqa: BLE001
            self.finished.emit(False, str(exc), [])


class EdgeActionWorker(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(
        self,
        host: str,
        user: str,
        password: str,
        compose_path: str,
        action: ContainerAction,
        service: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.host = host
        self.user = user
        self.password = password
        self.compose_path = compose_path
        self.action = action
        self.service = service

    def run(self) -> None:
        if self.service is None:
            ok, message = run_edge_compose_action_all(
                self.host,
                self.user,
                self.password,
                self.compose_path,
                self.action,
            )
        else:
            ok, message = run_edge_compose_action(
                self.host,
                self.user,
                self.password,
                self.compose_path,
                self.service,
                self.action,
            )
        self.finished.emit(ok, message)
