"""Record local Docker container logs."""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from typing import Callable, Iterable, Optional

from nexus_toolkit.app_state import app_state
from nexus_toolkit.utils import new_recording_dir


class LocalLogRecorder:
    def __init__(self) -> None:
        self._threads: list[threading.Thread] = []
        self._processes: list[subprocess.Popen] = []
        self._stop_event = threading.Event()
        self.recording_dir: Optional[Path] = None

    @property
    def recording(self) -> bool:
        return bool(self._threads) and not self._stop_event.is_set()

    def start(
        self,
        containers: Iterable[str],
        on_status: Callable[[str], None],
        recording_dir: Optional[Path] = None,
    ) -> Path:
        if self.recording:
            raise RuntimeError("Recording already in progress")

        self._stop_event.clear()
        self.recording_dir = recording_dir or new_recording_dir()
        app_state.set_recording_path(self.recording_dir)
        on_status(f"Recording to {self.recording_dir}")

        for container in containers:
            thread = threading.Thread(
                target=self._record_container,
                args=(container, self.recording_dir, on_status),
                daemon=True,
            )
            self._threads.append(thread)
            thread.start()

        return self.recording_dir

    def stop(self, on_status: Callable[[str], None]) -> Optional[Path]:
        self._stop_event.set()
        for process in self._processes:
            if process.poll() is None:
                process.terminate()
        for thread in self._threads:
            thread.join(timeout=5)
        self._threads.clear()
        self._processes.clear()
        path = self.recording_dir
        if path:
            on_status(f"Recording stopped: {path}")
        return path

    def _record_container(
        self,
        container: str,
        directory: Path,
        on_status: Callable[[str], None],
    ) -> None:
        log_file = directory / f"{container}.log"
        try:
            process = subprocess.Popen(
                ["docker", "logs", "-f", "--timestamps", container],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            self._processes.append(process)
            with log_file.open("w", encoding="utf-8") as handle:
                handle.write(f"# Container: {container}\n")
                assert process.stdout is not None
                for line in process.stdout:
                    if self._stop_event.is_set():
                        break
                    handle.write(line)
                    handle.flush()
            if process.poll() is None:
                process.terminate()
        except FileNotFoundError:
            on_status(f"docker not found while recording {container}")
        except Exception as exc:  # noqa: BLE001
            on_status(f"Error recording {container}: {exc}")
