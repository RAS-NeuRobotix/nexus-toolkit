"""Reset Nexus SQLite database under /opt/ras/db/nexus-core."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from nexus_toolkit.paths import NEXUS_DB_FILE
from nexus_toolkit.services.container_control import run_compose_action_all
from nexus_toolkit.services.sudo_auth import authenticate_sudo, is_sudo_cached


def _db_sidecar_paths(db_file: Path) -> list[Path]:
    return [db_file, Path(f"{db_file}-wal"), Path(f"{db_file}-shm")]


def delete_nexus_database_file(db_file: Path = NEXUS_DB_FILE) -> tuple[bool, str]:
    """Delete nexus.db (and SQLite sidecars) with sudo. Requires cached sudo."""
    targets = [path for path in _db_sidecar_paths(db_file) if path.exists()]
    if not targets:
        return True, f"Database already absent: {db_file}"

    try:
        result = subprocess.run(
            ["sudo", "-n", "rm", "-f", *[str(path) for path in targets]],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return False, f"Timed out while deleting {db_file}"
    except FileNotFoundError:
        return False, "sudo command not found"

    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        return False, message or f"Failed to delete {db_file}"

    remaining = [str(path) for path in targets if path.exists()]
    if remaining:
        return False, f"Still present after delete: {', '.join(remaining)}"
    return True, f"Deleted database: {db_file}"


def reset_nexus_database(
    password: str | None = None,
    on_status: Callable[[str], None] | None = None,
) -> tuple[bool, str]:
    """Stop stack → delete DB → start stack. Reports progress via on_status."""

    def status(message: str) -> None:
        if on_status:
            on_status(message)

    if not is_sudo_cached():
        if not password:
            return False, "Sudo password required"
        ok, message = authenticate_sudo(password)
        if not ok:
            return False, message
        status(message)

    status("Stopping all Nexus services...")
    ok, message = run_compose_action_all("stop")
    status(message)
    if not ok:
        return False, message

    status(f"Deleting database {NEXUS_DB_FILE}...")
    ok, message = delete_nexus_database_file()
    status(message)
    if not ok:
        status("Delete failed — attempting to start services again...")
        start_ok, start_msg = run_compose_action_all("start")
        status(start_msg)
        return False, f"{message}\n{start_msg}"

    status("Starting all Nexus services...")
    ok, message = run_compose_action_all("start")
    status(message)
    if not ok:
        return False, message

    return True, "Database deleted and system restarted"
