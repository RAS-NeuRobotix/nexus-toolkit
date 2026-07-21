"""Run the Nexus frontend dev server (npm run dev)."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
from pathlib import Path
from typing import IO, Optional


class FrontendDevRunner:
    def __init__(self) -> None:
        self._process: Optional[subprocess.Popen[str]] = None

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @property
    def stdout(self) -> Optional[IO[str]]:
        return None if self._process is None else self._process.stdout

    def start(self, app_dir: Path) -> tuple[bool, str]:
        if self.running:
            return False, "Frontend dev server is already running"

        if not app_dir.is_dir():
            return False, f"Frontend directory not found: {app_dir}"

        if not (app_dir / "package.json").is_file():
            return False, f"package.json not found in {app_dir}"

        if shutil.which("npm") is None:
            return False, "npm not found in PATH"

        try:
            self._process = subprocess.Popen(
                ["npm", "run", "dev"],
                cwd=app_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                preexec_fn=os.setsid,
                env=os.environ.copy(),
            )
        except OSError as exc:
            self._process = None
            return False, str(exc)

        return True, f"Started npm run dev in {app_dir}"

    def wait(self) -> int:
        if self._process is None:
            return 1
        return self._process.wait()

    def stop(self) -> None:
        if not self.running or self._process is None:
            return
        try:
            os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            self._process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(self._process.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
            self._process.kill()
        finally:
            self._process = None
