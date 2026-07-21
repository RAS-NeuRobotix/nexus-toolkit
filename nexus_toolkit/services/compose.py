"""Read Nexus services from docker-compose.yml."""

from __future__ import annotations

from pathlib import Path

import yaml

from nexus_toolkit.paths import COMPOSE_FILE, DEFAULT_CONTAINERS


def get_compose_container_names(compose_file: Path | None = None) -> list[str]:
    """Return container names defined in the Nexus docker-compose file."""
    path = compose_file or COMPOSE_FILE
    if not path.is_file():
        return list(DEFAULT_CONTAINERS)

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return list(DEFAULT_CONTAINERS)

    services = data.get("services") or {}
    names: list[str] = []
    for service_key, service in services.items():
        if not isinstance(service, dict):
            continue
        names.append(str(service.get("container_name") or service_key))
    return names


def get_compose_service_names(compose_file: Path | None = None) -> list[str]:
    """Return docker-compose service keys in file order."""
    path = compose_file or COMPOSE_FILE
    if not path.is_file():
        return list(DEFAULT_CONTAINERS)

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return list(DEFAULT_CONTAINERS)

    services = data.get("services") or {}
    return [str(name) for name, service in services.items() if isinstance(service, dict)]


def get_compose_service_entries(compose_file: Path | None = None) -> list[tuple[str, str]]:
    """Return (service_name, container_name) pairs in compose order."""
    path = compose_file or COMPOSE_FILE
    if not path.is_file():
        return [(name, name) for name in DEFAULT_CONTAINERS]

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return [(name, name) for name in DEFAULT_CONTAINERS]

    services = data.get("services") or {}
    entries: list[tuple[str, str]] = []
    for service_key, service in services.items():
        if not isinstance(service, dict):
            continue
        container_name = str(service.get("container_name") or service_key)
        entries.append((str(service_key), container_name))
    return entries
