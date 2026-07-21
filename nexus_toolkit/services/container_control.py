"""Control individual Nexus docker-compose services."""

from __future__ import annotations

import subprocess
import time
from typing import Literal

from nexus_toolkit.paths import COMPOSE_FILE
from nexus_toolkit.services.compose import get_compose_service_names

ContainerAction = Literal["stop", "start", "restart"]

_COMPOSE_BATCH_SIZE = 3
_COMPOSE_BATCH_PAUSE_SECONDS = 2


def run_compose_action(service: str, action: ContainerAction) -> tuple[bool, str]:
    cmd = ["docker", "compose", "-f", str(COMPOSE_FILE), action, service]
    success, message = _run_compose_command(cmd, timeout=120)
    if success:
        return True, f"{service}: {action} completed"
    return False, message or f"Failed to {action} {service}"


def run_compose_action_all(action: ContainerAction) -> tuple[bool, str]:
    if not COMPOSE_FILE.is_file():
        return False, f"docker-compose not found: {COMPOSE_FILE}"

    if action == "stop":
        cmd = ["docker", "compose", "-f", str(COMPOSE_FILE), "stop"]
        success, message = _run_compose_command(cmd, timeout=300)
        if success:
            return True, "All services stopped"
        return False, message or "Failed to stop all services"

    services = get_compose_service_names()
    if not services:
        return False, "No services found in docker-compose.yml"

    for index in range(0, len(services), _COMPOSE_BATCH_SIZE):
        batch = services[index : index + _COMPOSE_BATCH_SIZE]
        cmd = ["docker", "compose", "-f", str(COMPOSE_FILE), action, *batch]
        success, message = _run_compose_command(cmd, timeout=180)
        if not success:
            return False, message or f"Failed to {action} services: {', '.join(batch)}"

        remaining = len(services) - (index + len(batch))
        if remaining > 0:
            time.sleep(_COMPOSE_BATCH_PAUSE_SECONDS)

    label = "started" if action == "start" else "restarted"
    return True, f"All services {label}"


def _run_compose_command(cmd: list[str], timeout: int) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return False, "docker command not found"
    except subprocess.TimeoutExpired:
        return False, f"Timed out while running: {' '.join(cmd)}"

    output = (result.stdout or result.stderr or "").strip()
    if result.returncode == 0:
        return True, output

    return False, output or f"Command failed (exit code {result.returncode})"
