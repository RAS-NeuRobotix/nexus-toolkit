"""Sudo authentication helpers for deploy operations."""

from __future__ import annotations

import getpass
import subprocess
from pathlib import Path

RAS_APP_DIR = Path("/opt/ras/app")


def is_sudo_cached() -> bool:
    result = subprocess.run(
        ["sudo", "-n", "true"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.returncode == 0


def authenticate_sudo(password: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["sudo", "-S", "-v"],
            input=f"{password}\n",
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return False, "Sudo authentication timed out"
    except FileNotFoundError:
        return False, "sudo command not found"

    if result.returncode == 0:
        return True, "Sudo authenticated"
    message = (result.stderr or result.stdout or "").strip()
    return False, message or "Wrong sudo password"


def prepare_ras_permissions() -> tuple[bool, str]:
    """Set /opt/ras/app ownership to the current user before DeployManager runs."""
    user = getpass.getuser()
    if not RAS_APP_DIR.is_dir():
        return True, f"No {RAS_APP_DIR} directory to update"

    try:
        result = subprocess.run(
            ["sudo", "-n", "chown", "-R", f"{user}:{user}", str(RAS_APP_DIR)],
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        return False, f"Timed out while setting ownership of {RAS_APP_DIR}"
    except FileNotFoundError:
        return False, "sudo command not found"

    if result.returncode == 0:
        return True, f"Ownership of {RAS_APP_DIR} set to {user}:{user}"
    message = (result.stderr or result.stdout or "").strip()
    return False, message or f"Failed to set ownership of {RAS_APP_DIR}"


def ensure_sudo_for_deploy(password: str | None = None) -> tuple[bool, str]:
    if is_sudo_cached():
        return prepare_ras_permissions()

    if not password:
        return False, "Sudo password required"

    ok, message = authenticate_sudo(password)
    if not ok:
        return False, message

    return prepare_ras_permissions()
