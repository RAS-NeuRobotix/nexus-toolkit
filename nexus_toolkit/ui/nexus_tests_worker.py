"""Background workers for nexus-tests collect / run / git."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from nexus_toolkit.services.nexus_tests import (
    TestRunOptions,
    TestRunSummary,
    collect_tests,
    git_clone_or_pull,
    run_tests,
)


class TestsGitWorker(QThread):
    line = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, repo_dir: Path, git_url: str, parent=None) -> None:
        super().__init__(parent)
        self.repo_dir = repo_dir
        self.git_url = git_url

    def run(self) -> None:
        ok, message = git_clone_or_pull(
            self.repo_dir,
            self.git_url,
            on_line=self.line.emit,
        )
        self.finished.emit(ok, message)


class TestsCollectWorker(QThread):
    line = pyqtSignal(str)
    finished = pyqtSignal(bool, list, str)

    def __init__(
        self,
        repo_dir: Path,
        suite_path: str,
        marker_expression: str,
        drone: bool,
        lab: bool,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.repo_dir = repo_dir
        self.suite_path = suite_path
        self.marker_expression = marker_expression
        self.drone = drone
        self.lab = lab

    def run(self) -> None:
        ok, collected, message = collect_tests(
            self.repo_dir,
            suite_path=self.suite_path,
            marker_expression=self.marker_expression,
            drone=self.drone,
            lab=self.lab,
            on_line=self.line.emit,
        )
        # Emit plain dicts so queued Qt signals never drop dataclass fields.
        payload = [
            {"nodeid": item.nodeid, "description": item.description} for item in collected
        ]
        self.finished.emit(ok, payload, message)


class TestsRunWorker(QThread):
    line = pyqtSignal(str)
    finished = pyqtSignal(bool, object)

    def __init__(
        self,
        repo_dir: Path,
        selected_nodeids: list[str],
        options: TestRunOptions,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.repo_dir = repo_dir
        self.selected_nodeids = selected_nodeids
        self.options = options

    def run(self) -> None:
        ok, summary = run_tests(
            self.repo_dir,
            self.selected_nodeids,
            self.options,
            on_line=self.line.emit,
        )
        self.finished.emit(ok, summary)
