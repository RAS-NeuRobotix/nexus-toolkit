"""Settings dialog for Cursor API key and local Front path."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from nexus_toolkit.config import get_cloud_repo_url, get_cursor_api_key, get_cursor_model, save_config
from nexus_toolkit.paths import (
    FRONTEND_APP_DIR_LEGACY,
    FRONTEND_APP_DIR_NEXUS,
    is_frontend_app_dir,
    resolve_frontend_app_dir,
)
from nexus_toolkit.services.cursor_agent import validate_api_key
from nexus_toolkit.ui.widgets import make_muted_label, make_secondary_button


class SettingsDialog(QDialog):
    def __init__(self, config: dict, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Settings")
        self.setMinimumWidth(640)
        self.resize(680, 360)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.api_key_edit = QLineEdit(get_cursor_api_key(config))
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("cursor_...")

        self.model_edit = QLineEdit(get_cursor_model(config))
        self.cloud_repo_edit = QLineEdit(get_cloud_repo_url(config))
        self.cloud_repo_edit.setPlaceholderText("https://github.com/org/repo")

        form.addRow("Cursor API Key:", self.api_key_edit)
        form.addRow("Model:", self.model_edit)
        form.addRow("Cloud repo (Jira):", self.cloud_repo_edit)

        frontend_cfg = config.get("frontend") or {}
        saved_front = str(frontend_cfg.get("app_dir") or "").strip()
        self.front_dir_edit = QLineEdit(saved_front)
        self.front_dir_edit.setPlaceholderText(
            f"Empty = auto ({FRONTEND_APP_DIR_NEXUS.name} under ~/nexus or ~/)"
        )
        browse_btn = make_secondary_button("Browse…")
        browse_btn.clicked.connect(self._browse_front_dir)
        front_row = QWidget()
        front_layout = QHBoxLayout(front_row)
        front_layout.setContentsMargins(0, 0, 0, 0)
        front_layout.addWidget(self.front_dir_edit, stretch=1)
        front_layout.addWidget(browse_btn)
        form.addRow("Front app-tactical:", front_row)
        layout.addLayout(form)

        layout.addWidget(
            make_muted_label(
                "נתיב אישי נשמר ב-~/.config/nexus-toolkit/config.yaml.\n"
                "ריק = זיהוי אוטומטי:\n"
                f"  1) {FRONTEND_APP_DIR_NEXUS}\n"
                f"  2) {FRONTEND_APP_DIR_LEGACY}"
            )
        )
        self.front_resolved_label = make_muted_label("")
        layout.addWidget(self.front_resolved_label)
        self._refresh_front_resolved()
        self.front_dir_edit.textChanged.connect(lambda _t: self._refresh_front_resolved())

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        test_btn = buttons.addButton("Test Connection", QDialogButtonBox.ButtonRole.ActionRole)
        test_btn.clicked.connect(self._test_connection)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse_front_dir(self) -> None:
        start = self.front_dir_edit.text().strip() or str(resolve_frontend_app_dir(self.config))
        path = QFileDialog.getExistingDirectory(self, "Select app-tactical directory", start)
        if path:
            self.front_dir_edit.setText(path)

    def _preview_config(self) -> dict:
        preview = {
            **self.config,
            "frontend": {
                **(self.config.get("frontend") or {}),
                "app_dir": self.front_dir_edit.text().strip(),
            },
        }
        return preview

    def _refresh_front_resolved(self) -> None:
        resolved = resolve_frontend_app_dir(self._preview_config())
        ok = is_frontend_app_dir(resolved)
        status = "found" if ok else "not found (Start Front may fail)"
        self.front_resolved_label.setText(f"Will use: {resolved}  —  {status}")

    def _test_connection(self) -> None:
        ok, message = validate_api_key(self.api_key_edit.text().strip())
        self.status_label.setText(message)
        if not ok:
            QMessageBox.warning(self, "Connection Failed", message)

    def _save(self) -> None:
        front_dir = self.front_dir_edit.text().strip()
        if front_dir:
            path = Path(front_dir).expanduser()
            if not is_frontend_app_dir(path):
                reply = QMessageBox.question(
                    self,
                    "Front path",
                    "הנתיב לא נראה כמו app-tactical תקין (חסר package.json).\n"
                    "לשמור בכל זאת?",
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return

        self.config.setdefault("cursor", {})
        self.config["cursor"]["api_key"] = self.api_key_edit.text().strip()
        self.config["cursor"]["model"] = self.model_edit.text().strip() or "composer-2.5"
        self.config["cursor"]["cloud_repo"] = self.cloud_repo_edit.text().strip()

        self.config.setdefault("frontend", {})
        self.config["frontend"]["app_dir"] = front_dir

        save_config(self.config)
        self.accept()
