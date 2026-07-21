"""SSH helpers for Edge (drone) control."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import paramiko


def connect_edge(host: str, user: str, password: str, timeout: int = 20) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=host,
        username=user,
        password=password,
        timeout=timeout,
        look_for_keys=False,
        allow_agent=False,
    )
    return client


@contextmanager
def edge_ssh_session(host: str, user: str, password: str, timeout: int = 20) -> Iterator[paramiko.SSHClient]:
    client = connect_edge(host, user, password, timeout=timeout)
    try:
        yield client
    finally:
        client.close()


def ssh_exec(
    client: paramiko.SSHClient,
    command: str,
    *,
    timeout: int = 120,
) -> tuple[int, str, str]:
    _, stdout, stderr = client.exec_command(command, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    return code, out, err


def test_edge_connection(host: str, user: str, password: str) -> tuple[bool, str]:
    if not host or not user:
        return False, "Host and user are required"
    if not password:
        return False, "Password is required"
    try:
        with edge_ssh_session(host, user, password) as client:
            code, out, err = ssh_exec(client, "echo ok", timeout=15)
            if code == 0 and out.strip() == "ok":
                return True, f"Connected to {user}@{host}"
            return False, (err or out or "SSH test failed").strip()
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
