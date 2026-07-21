"""Docker container version and status info."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Iterable

from nexus_toolkit.services.compose import get_compose_service_entries


@dataclass
class ContainerInfo:
    name: str
    service: str
    image: str
    status: str
    running: bool


def _inspect_container(service: str, name: str) -> ContainerInfo:
    try:
        result = subprocess.run(
            [
                "docker",
                "inspect",
                "--format",
                "{{.Config.Image}}\t{{.State.Status}}",
                name,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return ContainerInfo(name, service, "(not found)", "missing", False)
        image, _, status = result.stdout.strip().partition("\t")
        status = status or "unknown"
        return ContainerInfo(name, service, image, status, status == "running")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ContainerInfo(name, service, "(error)", "error", False)


def get_container_versions(names: Iterable[str] | None = None) -> list[ContainerInfo]:
    if names is not None:
        targets = [(name, name) for name in names]
    else:
        targets = get_compose_service_entries()
    return [_inspect_container(service, container) for service, container in targets]
