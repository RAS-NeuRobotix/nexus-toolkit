"""Settings dialog for Cursor API key."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from nexus_toolkit.config import get_cloud_repo_url, get_cursor_api_key, get_cursor_model, save_config
from nexus_toolkit.services.cursor_agent import validate_api_key


class SettingsDialog(QDialog):
    def __init__(self, config: dict, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Settings")
        self.resize(520, 260)

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
        layout.addLayout(form)

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

    def _test_connection(self) -> None:
        ok, message = validate_api_key(self.api_key_edit.text().strip())
        self.status_label.setText(message)
        if not ok:
            QMessageBox.warning(self, "Connection Failed", message)

    def _save(self) -> None:
        self.config.setdefault("cursor", {})
        self.config["cursor"]["api_key"] = self.api_key_edit.text().strip()
        self.config["cursor"]["model"] = self.model_edit.text().strip() or "composer-2.5"
        self.config["cursor"]["cloud_repo"] = self.cloud_repo_edit.text().strip()
        save_config(self.config)
        self.accept()
