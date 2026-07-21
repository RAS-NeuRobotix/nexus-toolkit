"""Azure CLI authentication helpers."""

from __future__ import annotations

import json
import subprocess
import threading
from typing import Callable, Optional


def check_azure_login() -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["az", "account", "show", "--output", "json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return False, "Not logged in to Azure"
        data = json.loads(result.stdout or "{}")
        name = data.get("name") or data.get("id") or "unknown"
        return True, str(name)
    except FileNotFoundError:
        return False, "Azure CLI (az) not installed"
    except (json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)


def start_az_login(on_line: Optional[Callable[[str], None]] = None) -> threading.Thread:
    def _run() -> None:
        try:
            process = subprocess.Popen(
                ["az", "login"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            assert process.stdout is not None
            for line in process.stdout:
                if on_line:
                    on_line(line.rstrip("\n"))
            process.wait()
        except FileNotFoundError:
            if on_line:
                on_line("Azure CLI (az) not found")

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread
