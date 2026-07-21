"""Record drone platform-manager logs via SSH."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Optional

import paramiko

from nexus_toolkit.app_state import app_state
from nexus_toolkit.utils import new_recording_dir


def _ssh_connect(client: paramiko.SSHClient, host: str, user: str, password: str) -> None:
    client.connect(
        hostname=host,
        username=user,
        password=password,
        timeout=20,
        look_for_keys=False,
        allow_agent=False,
    )


class DroneLogRecorder:
    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._client: Optional[paramiko.SSHClient] = None
        self._stop_event = threading.Event()
        self.recording_dir: Optional[Path] = None

    @property
    def recording(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @staticmethod
    def test_connection(host: str, user: str, password: str) -> tuple[bool, str]:
        if not password:
            return False, "Password is required"

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            _ssh_connect(client, host, user, password)
            _, stdout, stderr = client.exec_command("echo ok", timeout=10)
            out = stdout.read().decode().strip()
            err = stderr.read().decode().strip()
            if out == "ok":
                return True, "SSH connection successful"
            return False, err or "SSH test failed"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)
        finally:
            client.close()

    def start(
        self,
        host: str,
        user: str,
        password: str,
        on_status: Callable[[str], None],
        recording_dir: Optional[Path] = None,
    ) -> Path:
        if self.recording:
            raise RuntimeError("Drone recording already in progress")
        if not password:
            raise ValueError("Password is required")

        self._stop_event.clear()
        base_dir = recording_dir or new_recording_dir()
        self.recording_dir = base_dir
        app_state.set_recording_path(base_dir)

        self._thread = threading.Thread(
            target=self._record,
            args=(host, user, password, base_dir, on_status),
            daemon=True,
        )
        self._thread.start()
        on_status(f"Drone recording to {base_dir}")
        return base_dir

    def stop(self, on_status: Callable[[str], None]) -> Optional[Path]:
        self._stop_event.set()
        if self._client:
            try:
                self._client.close()
            except Exception:  # noqa: BLE001
                pass
            self._client = None
        if self._thread:
            self._thread.join(timeout=10)
            self._thread = None
        path = self.recording_dir
        if path:
            on_status(f"Drone recording stopped: {path}")
        return path

    def _record(
        self,
        host: str,
        user: str,
        password: str,
        directory: Path,
        on_status: Callable[[str], None],
    ) -> None:
        log_file = directory / "platform-manager.log"
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            _ssh_connect(client, host, user, password)
            self._client = client
            transport = client.get_transport()
            if not transport:
                on_status("SSH transport unavailable")
                return
            channel = transport.open_session()
            channel.exec_command("docker logs -f --timestamps platform-manager")
            channel.settimeout(1.0)
            with log_file.open("w", encoding="utf-8") as handle:
                handle.write(f"# Drone: {user}@{host}\n# Container: platform-manager\n")
                while not self._stop_event.is_set():
                    try:
                        if channel.recv_ready():
                            data = channel.recv(4096).decode("utf-8", errors="replace")
                            handle.write(data)
                            handle.flush()
                        elif channel.exit_status_ready():
                            break
                    except Exception:  # noqa: BLE001
                        continue
        except Exception as exc:  # noqa: BLE001
            on_status(f"Drone recording error: {exc}")
        finally:
            try:
                client.close()
            except Exception:  # noqa: BLE001
                pass
            self._client = None
