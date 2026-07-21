"""Deploy Edge release package over SSH (tar → load → edge_up)."""

from __future__ import annotations

import shlex
import tarfile
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from nexus_toolkit.services.edge_ssh import edge_ssh_session

EDGE_RAS_DIR = "/opt/ras"
OnLine = Callable[[str], None]
# overall percent 0-100, short stage label
OnProgress = Callable[[int, str], None]

_STAGE_UPLOAD = (0, 45)
_STAGE_EXTRACT = (45, 60)
_STAGE_LOAD = (60, 85)
_STAGE_EDGE_UP = (85, 100)


def _map_stage(bounds: tuple[int, int], fraction: float) -> int:
    start, end = bounds
    fraction = max(0.0, min(1.0, fraction))
    return int(start + (end - start) * fraction)


class EdgeDeployRunner:
    def __init__(self) -> None:
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run_blocking(
        self,
        *,
        host: str,
        user: str,
        password: str,
        local_tar: Path,
        on_line: Optional[OnLine] = None,
        on_progress: Optional[OnProgress] = None,
    ) -> tuple[bool, str]:
        self._cancel.clear()
        log = on_line or (lambda _msg: None)
        progress = on_progress or (lambda _pct, _label: None)

        if not local_tar.is_file():
            return False, f"Tar file not found: {local_tar}"

        tar_name = local_tar.name
        if not tar_name.endswith(".tar"):
            return False, "Edge package must be a .tar file"

        package_dir_name = tar_name[: -len(".tar")]
        remote_tar = f"{EDGE_RAS_DIR}/{tar_name}"
        remote_dir = f"{EDGE_RAS_DIR}/{package_dir_name}"

        try:
            member_count = self._count_tar_members(local_tar)
            progress(0, "Starting…")

            with edge_ssh_session(host, user, password, timeout=30) as client:
                if self._cancel.is_set():
                    return False, "Edge update cancelled"

                log(f"=== Upload {tar_name} → {remote_tar} ===")
                progress(_STAGE_UPLOAD[0], "Uploading package…")
                ok, message = self._upload_tar(
                    client, local_tar, remote_tar, password, log, progress
                )
                if not ok:
                    return False, message
                progress(_STAGE_UPLOAD[1], "Upload complete")

                if self._cancel.is_set():
                    return False, "Edge update cancelled"

                log(f"=== Extract: tar xvf {tar_name} (in {EDGE_RAS_DIR}) ===")
                progress(_STAGE_EXTRACT[0], "Extracting package…")
                ok, message = self._extract_tar(
                    client, password, tar_name, member_count, log, progress
                )
                if not ok:
                    return False, message
                progress(_STAGE_EXTRACT[1], "Extract complete")

                if self._cancel.is_set():
                    return False, "Edge update cancelled"

                log(f"=== sudo ./load-to-standalone.sh -l (in {remote_dir}) ===")
                progress(_STAGE_LOAD[0], "Loading images…")
                ok, message = self._run_load_script(
                    client, password, remote_dir, log, progress
                )
                if not ok:
                    return False, message
                progress(_STAGE_LOAD[1], "Images loaded")

                if self._cancel.is_set():
                    return False, "Edge update cancelled"

                log("=== edge_up ===")
                progress(_STAGE_EDGE_UP[0], "Starting Edge services…")
                ok, message = self._run_edge_up(client, log, progress)
                if not ok:
                    return False, message

            progress(100, "Done")
            return True, "Edge update completed"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    @staticmethod
    def _count_tar_members(local_tar: Path) -> int:
        try:
            with tarfile.open(local_tar, "r:*") as archive:
                return max(len(archive.getmembers()), 1)
        except (OSError, tarfile.TarError):
            return 1

    def _upload_tar(
        self,
        client,
        local_tar: Path,
        remote_tar: str,
        password: str,
        log: OnLine,
        progress: OnProgress,
    ) -> tuple[bool, str]:
        total = max(local_tar.stat().st_size, 1)
        last_pct = [-1]

        def on_bytes(transferred: int, _remote_total: int) -> None:
            fraction = min(1.0, transferred / total)
            overall = _map_stage(_STAGE_UPLOAD, fraction)
            step = int(fraction * 100)
            if step != last_pct[0] and (step % 1 == 0 or step == 100):
                # update every 1% for smoother bar; throttle log to 5%
                if step == 100 or step % 5 == 0 or step != last_pct[0]:
                    if step == 100 or last_pct[0] < 0 or step // 5 != last_pct[0] // 5:
                        log(f"Upload progress: {step}%")
                last_pct[0] = step
                progress(overall, f"Uploading… {step}%")

        sftp = client.open_sftp()
        try:
            try:
                sftp.put(str(local_tar), remote_tar, callback=on_bytes)
                log(f"Uploaded to {remote_tar}")
                return True, "uploaded"
            except OSError as exc:
                log(f"Direct upload to {EDGE_RAS_DIR} failed ({exc}); using /tmp + sudo mv")
                tmp_remote = f"/tmp/{local_tar.name}"
                last_pct[0] = -1
                sftp.put(str(local_tar), tmp_remote, callback=on_bytes)
                log(f"Uploaded to {tmp_remote}")
        finally:
            sftp.close()

        move_cmd = f"mv {shlex.quote(f'/tmp/{local_tar.name}')} {shlex.quote(remote_tar)}"
        code, out, err = self._sudo_exec(client, password, move_cmd, timeout=120)
        text = (out or err or "").strip()
        if code != 0:
            return False, text or f"Failed to move package to {remote_tar}"
        log(f"Moved package to {remote_tar}")
        return True, "uploaded"

    def _extract_tar(
        self,
        client,
        password: str,
        tar_name: str,
        member_count: int,
        log: OnLine,
        progress: OnProgress,
    ) -> tuple[bool, str]:
        cmd = f"cd {shlex.quote(EDGE_RAS_DIR)} && tar xvf {shlex.quote(tar_name)}"
        code, text = self._stream_command(
            client,
            cmd,
            log=log,
            on_line_count=lambda n: progress(
                _map_stage(_STAGE_EXTRACT, n / max(member_count, 1)),
                f"Extracting… {min(n, member_count)}/{member_count}",
            ),
            timeout=600,
        )
        if code == 0:
            return True, "extracted"

        log("tar without sudo failed — retrying with sudo")
        code, text = self._stream_sudo(
            client,
            password,
            f"tar xvf {shlex.quote(tar_name)}",
            cwd=EDGE_RAS_DIR,
            log=log,
            on_line_count=lambda n: progress(
                _map_stage(_STAGE_EXTRACT, n / max(member_count, 1)),
                f"Extracting… {min(n, member_count)}/{member_count}",
            ),
            timeout=600,
        )
        if code != 0:
            return False, text or "Failed to extract tar"
        return True, "extracted"

    def _run_load_script(
        self,
        client,
        password: str,
        remote_dir: str,
        log: OnLine,
        progress: OnProgress,
    ) -> tuple[bool, str]:
        started = time.monotonic()

        def on_count(n: int) -> None:
            # Soft progress inside load stage — no true total available.
            elapsed = time.monotonic() - started
            soft = min(0.95, elapsed / 600.0)  # approach end of stage over ~10 min
            soft = max(soft, min(0.9, n / 200.0))
            progress(_map_stage(_STAGE_LOAD, soft), f"Loading images… ({n} log lines)")

        code, text = self._stream_sudo(
            client,
            password,
            "./load-to-standalone.sh -l",
            cwd=remote_dir,
            log=log,
            on_line_count=on_count,
            timeout=3600,
        )
        if code != 0:
            return False, text or "load-to-standalone.sh failed"
        return True, "images loaded"

    def _run_edge_up(self, client, log: OnLine, progress: OnProgress) -> tuple[bool, str]:
        started = time.monotonic()

        def on_count(n: int) -> None:
            elapsed = time.monotonic() - started
            soft = min(0.95, elapsed / 300.0)
            soft = max(soft, min(0.9, n / 100.0))
            progress(_map_stage(_STAGE_EDGE_UP, soft), f"edge_up… ({n} log lines)")

        code, text = self._stream_command(
            client,
            "bash -lic 'edge_up'",
            log=log,
            on_line_count=on_count,
            timeout=1800,
        )
        if code != 0:
            return False, text or "edge_up failed"
        return True, "edge_up completed"

    def _stream_command(
        self,
        client,
        command: str,
        *,
        log: OnLine,
        on_line_count: Callable[[int], None] | None = None,
        timeout: int = 300,
    ) -> tuple[int, str]:
        _stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        return self._consume_streams(stdout, stderr, log, on_line_count)

    def _stream_sudo(
        self,
        client,
        password: str,
        command: str,
        *,
        cwd: str | None = None,
        log: OnLine,
        on_line_count: Callable[[int], None] | None = None,
        timeout: int = 300,
    ) -> tuple[int, str]:
        if cwd:
            wrapped = f"cd {shlex.quote(cwd)} && sudo -S -p '' {command}"
        else:
            wrapped = f"sudo -S -p '' {command}"
        stdin, stdout, stderr = client.exec_command(wrapped, timeout=timeout)
        stdin.write(password + "\n")
        stdin.flush()
        stdin.channel.shutdown_write()
        return self._consume_streams(stdout, stderr, log, on_line_count)

    def _consume_streams(
        self,
        stdout,
        stderr,
        log: OnLine,
        on_line_count: Callable[[int], None] | None,
    ) -> tuple[int, str]:
        collected: list[str] = []
        count = 0
        channel = stdout.channel
        while not channel.exit_status_ready() or channel.recv_ready() or channel.recv_stderr_ready():
            if self._cancel.is_set():
                try:
                    channel.close()
                except Exception:  # noqa: BLE001
                    pass
                return 1, "Edge update cancelled"

            chunk_out = ""
            chunk_err = ""
            if channel.recv_ready():
                chunk_out = channel.recv(4096).decode("utf-8", errors="replace")
            if channel.recv_stderr_ready():
                chunk_err = channel.recv_stderr(4096).decode("utf-8", errors="replace")

            for chunk in (chunk_out, chunk_err):
                if not chunk:
                    continue
                for line in chunk.splitlines():
                    line = line.rstrip()
                    if not line:
                        continue
                    collected.append(line)
                    log(line)
                    count += 1
                    if on_line_count:
                        on_line_count(count)

            if not chunk_out and not chunk_err:
                time.sleep(0.05)

        code = channel.recv_exit_status()
        # Drain leftovers
        leftover = stdout.read().decode("utf-8", errors="replace")
        leftover_err = stderr.read().decode("utf-8", errors="replace")
        for chunk in (leftover, leftover_err):
            for line in chunk.splitlines():
                line = line.rstrip()
                if line:
                    collected.append(line)
                    log(line)
                    count += 1
                    if on_line_count:
                        on_line_count(count)
        return code, "\n".join(collected)

    def _sudo_exec(
        self,
        client,
        password: str,
        command: str,
        *,
        cwd: str | None = None,
        timeout: int = 300,
    ) -> tuple[int, str, str]:
        if cwd:
            wrapped = f"cd {shlex.quote(cwd)} && sudo -S -p '' {command}"
        else:
            wrapped = f"sudo -S -p '' {command}"

        stdin, stdout, stderr = client.exec_command(wrapped, timeout=timeout)
        stdin.write(password + "\n")
        stdin.flush()
        stdin.channel.shutdown_write()
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        code = stdout.channel.recv_exit_status()
        return code, out, err
