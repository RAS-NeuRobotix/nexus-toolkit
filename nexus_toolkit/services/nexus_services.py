"""Shared Nexus Control services used across dialogs."""

from __future__ import annotations

from typing import Callable

from nexus_toolkit.services.deploy import DeployRunner
from nexus_toolkit.services.drone_logs import DroneLogRecorder
from nexus_toolkit.services.edge_deploy import EdgeDeployRunner
from nexus_toolkit.services.frontend_dev import FrontendDevRunner
from nexus_toolkit.services.local_logs import LocalLogRecorder


class NexusServices:
    def __init__(self, config: dict, on_recording_changed: Callable[[], None] | None = None) -> None:
        self.config = config
        self.on_recording_changed = on_recording_changed
        self.deploy_runner = DeployRunner()
        self.edge_deploy_runner = EdgeDeployRunner()
        self.frontend_runner = FrontendDevRunner()
        self.local_recorder = LocalLogRecorder()
        self.drone_recorder = DroneLogRecorder()

    def notify_recording_changed(self) -> None:
        if self.on_recording_changed:
            self.on_recording_changed()
