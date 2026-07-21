"""Control Edge (drone) docker-compose services over SSH."""

from __future__ import annotations

import json
import shlex
import time
from dataclasses import dataclass

from nexus_toolkit.services.container_control import ContainerAction
from nexus_toolkit.services.edge_ssh import edge_ssh_session, ssh_exec

DEFAULT_EDGE_COMPOSE = "/opt/ras/docker-compose.yml"

_COMPOSE_BATCH_SIZE = 3
_COMPOSE_BATCH_PAUSE_SECONDS = 2


@dataclass
class EdgeContainerInfo:
    name: str
    service: str
    image: str
    status: str
    running: bool


def _compose_prefix(compose_path: str) -> str:
    return f"docker compose -f {shlex.quote(compose_path)}"


def verify_edge_compose(host: str, user: str, password: str, compose_path: str) -> tuple[bool, str]:
    try:
        with edge_ssh_session(host, user, password) as client:
            code, out, err = ssh_exec(
                client,
                f"test -f {shlex.quote(compose_path)} && echo ok",
                timeout=20,
            )
            if code != 0 or out.strip() != "ok":
                detail = (err or out or "").strip()
                return False, detail or f"Compose file not found on Edge: {compose_path}"
            code, _, err = ssh_exec(client, "docker compose version", timeout=20)
            if code != 0:
                return False, (err or "docker compose not available on Edge").strip()
            return True, f"Compose ready: {compose_path}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def _list_service_names(client, compose_path: str) -> list[str]:
    code, out, err = ssh_exec(
        client,
        f"{_compose_prefix(compose_path)} config --services",
        timeout=60,
    )
    if code != 0:
        raise RuntimeError((err or out or "Failed to list compose services").strip())
    return [line.strip() for line in out.splitlines() if line.strip()]


def _ps_by_service(client, compose_path: str) -> dict[str, EdgeContainerInfo]:
    code, out, err = ssh_exec(
        client,
        f"{_compose_prefix(compose_path)} ps -a --format json",
        timeout=90,
    )
    if code != 0:
        # Older docker may not support json format — return empty and fall back later.
        return {}

    by_service: dict[str, EdgeContainerInfo] = {}
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            # Some versions return one JSON array.
            try:
                rows = json.loads(out)
            except json.JSONDecodeError:
                return {}
            if isinstance(rows, list):
                by_service = {}
                for item in rows:
                    info = _info_from_ps_row(item)
                    if info:
                        by_service[info.service] = info
                return by_service
            return {}

        info = _info_from_ps_row(data)
        if info:
            by_service[info.service] = info
    return by_service


def _info_from_ps_row(data: dict) -> EdgeContainerInfo | None:
    service = str(data.get("Service") or data.get("service") or "").strip()
    if not service:
        return None
    name = str(data.get("Name") or data.get("name") or service).strip()
    image = str(data.get("Image") or data.get("image") or "").strip() or "(unknown)"
    state = str(data.get("State") or data.get("state") or "").strip() or "unknown"
    status = str(data.get("Status") or data.get("status") or state).strip() or state
    running = state.lower() == "running" or status.lower().startswith("up")
    return EdgeContainerInfo(
        name=name,
        service=service,
        image=image,
        status=status,
        running=running,
    )


def list_edge_containers(
    host: str,
    user: str,
    password: str,
    compose_path: str = DEFAULT_EDGE_COMPOSE,
) -> list[EdgeContainerInfo]:
    with edge_ssh_session(host, user, password) as client:
        services = _list_service_names(client, compose_path)
        ps_map = _ps_by_service(client, compose_path)
        results: list[EdgeContainerInfo] = []
        for service in services:
            if service in ps_map:
                results.append(ps_map[service])
            else:
                results.append(
                    EdgeContainerInfo(
                        name=service,
                        service=service,
                        image="(not found)",
                        status="missing",
                        running=False,
                    )
                )
        return results


def run_edge_compose_action(
    host: str,
    user: str,
    password: str,
    compose_path: str,
    service: str,
    action: ContainerAction,
) -> tuple[bool, str]:
    cmd = f"{_compose_prefix(compose_path)} {action} {shlex.quote(service)}"
    try:
        with edge_ssh_session(host, user, password) as client:
            code, out, err = ssh_exec(client, cmd, timeout=180)
            text = (out or err or "").strip()
            if code == 0:
                return True, f"{service}: {action} completed"
            return False, text or f"Failed to {action} {service}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def run_edge_compose_action_all(
    host: str,
    user: str,
    password: str,
    compose_path: str,
    action: ContainerAction,
) -> tuple[bool, str]:
    try:
        with edge_ssh_session(host, user, password) as client:
            if action == "stop":
                code, out, err = ssh_exec(
                    client,
                    f"{_compose_prefix(compose_path)} stop",
                    timeout=300,
                )
                text = (out or err or "").strip()
                if code == 0:
                    return True, "All Edge services stopped"
                return False, text or "Failed to stop all Edge services"

            services = _list_service_names(client, compose_path)
            if not services:
                return False, "No services found in Edge compose file"

            for index in range(0, len(services), _COMPOSE_BATCH_SIZE):
                batch = services[index : index + _COMPOSE_BATCH_SIZE]
                quoted = " ".join(shlex.quote(name) for name in batch)
                code, out, err = ssh_exec(
                    client,
                    f"{_compose_prefix(compose_path)} {action} {quoted}",
                    timeout=240,
                )
                if code != 0:
                    text = (out or err or "").strip()
                    return False, text or f"Failed to {action} services: {', '.join(batch)}"
                remaining = len(services) - (index + len(batch))
                if remaining > 0:
                    time.sleep(_COMPOSE_BATCH_PAUSE_SECONDS)

            label = "started" if action == "start" else "restarted"
            return True, f"All Edge services {label}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
