"""DeployManager download and docker compose up."""

from __future__ import annotations

import re
import subprocess
import time
from typing import Callable, Optional

from nexus_toolkit.paths import COMPOSE_FILE, DEPLOY_MANAGER
from nexus_toolkit.services.compose import get_compose_service_names

ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")
COMPOSE_BATCH_SIZE = 3
COMPOSE_BATCH_PAUSE_SECONDS = 2


class DeployRunner:
    def __init__(self) -> None:
        self._process: Optional[subprocess.Popen[str]] = None

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def cancel(self) -> None:
        if self._process and self._process.poll() is None:
            self._process.terminate()

    def run_blocking(
        self,
        be_version: str,
        fe_version: str,
        project: Optional[str],
        on_line: Callable[[str], None],
    ) -> tuple[bool, str]:
        if not DEPLOY_MANAGER.is_file():
            return False, f"DeployManager not found: {DEPLOY_MANAGER}"

        if not COMPOSE_FILE.is_file():
            return False, f"docker-compose not found: {COMPOSE_FILE}"

        try:
            download_cmd = [
                str(DEPLOY_MANAGER),
                "download",
                "--be",
                be_version,
                "--fe",
                fe_version,
            ]
            if project:
                download_cmd.extend(["--project", project])

            on_line("=== DeployManager download ===")
            code = self._run_process(download_cmd, on_line)
            if code != 0:
                return False, f"Download failed with exit code {code}"

            on_line("\n=== docker compose up -d (gradual restart) ===")
            code = self._compose_up_gradually(on_line)
            if code != 0:
                return False, f"docker compose up failed with exit code {code}"

            return True, "System update completed successfully"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)
        finally:
            self._process = None

    def _compose_up_gradually(self, on_line: Callable[[str], None]) -> int:
        services = get_compose_service_names()
        if not services:
            on_line("No services found in docker-compose.yml")
            return 1

        for index in range(0, len(services), COMPOSE_BATCH_SIZE):
            batch = services[index : index + COMPOSE_BATCH_SIZE]
            on_line(f"Starting batch: {', '.join(batch)}")
            compose_cmd = ["docker", "compose", "-f", str(COMPOSE_FILE), "up", "-d", *batch]
            code = self._run_process(compose_cmd, on_line)
            if code != 0:
                return code

            remaining = len(services) - (index + len(batch))
            if remaining > 0:
                on_line(f"Waiting {COMPOSE_BATCH_PAUSE_SECONDS}s before next batch...")
                time.sleep(COMPOSE_BATCH_PAUSE_SECONDS)

        return 0

    def _run_process(self, cmd: list[str], on_line: Callable[[str], None]) -> int:
        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert self._process.stdout is not None
        for line in self._process.stdout:
            cleaned = ANSI_ESCAPE_RE.sub("", line).rstrip("\n")
            if cleaned:
                on_line(cleaned)
        return self._process.wait()


def check_docker() -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return True, "Docker is available"
        return False, result.stderr.strip() or "Docker is not running"
    except FileNotFoundError:
        return False, "docker command not found"
    except subprocess.TimeoutExpired:
        return False, "docker info timed out"
