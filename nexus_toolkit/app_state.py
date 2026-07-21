"""Global application state shared between tabs."""

from pathlib import Path
from typing import Optional


class AppState:
    """Singleton-like shared state for cross-tab data."""

    def __init__(self) -> None:
        self.last_recording_path: Optional[Path] = None

    def set_recording_path(self, path: Path) -> None:
        self.last_recording_path = path

    def has_recording(self) -> bool:
        return self.last_recording_path is not None and self.last_recording_path.is_dir()


app_state = AppState()
