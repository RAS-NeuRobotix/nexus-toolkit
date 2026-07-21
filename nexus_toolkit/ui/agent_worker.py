"""Background worker for Cursor agent calls."""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from nexus_toolkit.services.cursor_agent import run_agent_prompt


class AgentWorker(QThread):
    chunk = pyqtSignal(str)
    finished_ok = pyqtSignal(str)
    finished_err = pyqtSignal(str)

    def __init__(
        self,
        prompt: str,
        api_key: str,
        model: str,
        cloud_repo_url: str,
        *,
        fast: bool = False,
        local: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.prompt = prompt
        self.api_key = api_key
        self.model = model
        self.cloud_repo_url = cloud_repo_url
        self.fast = fast
        self.local = local

    def run(self) -> None:
        try:
            result = run_agent_prompt(
                self.prompt,
                self.api_key,
                self.model,
                self.cloud_repo_url,
                on_chunk=lambda text: self.chunk.emit(text),
                fast=self.fast,
                local=self.local,
            )
            self.finished_ok.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.finished_err.emit(str(exc))
