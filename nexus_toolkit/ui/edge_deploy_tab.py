"""Edge update tab — upload tar package and run load + edge_up."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from nexus_toolkit.config import save_config
from nexus_toolkit.services.edge_deploy import EDGE_RAS_DIR
from nexus_toolkit.services.nexus_services import NexusServices
from nexus_toolkit.ui.edge_deploy_worker import EdgeDeployWorker
from nexus_toolkit.ui.log_view import LogBridge, append_log_limited
from nexus_toolkit.ui.widgets import (
    PasswordLineEdit,
    confirm_action,
    make_log_view,
    make_muted_label,
    make_primary_button,
    make_secondary_button,
)


class EdgeDeployTab(QWidget):
    def __init__(self, services: NexusServices, parent=None) -> None:
        super().__init__(parent)
        self.services = services
        self._worker: EdgeDeployWorker | None = None
        self._tar_path: Path | None = None
        self._log_bridge = LogBridge()
        self._log_bridge.line.connect(self._append_log)

        layout = QVBoxLayout(self)

        layout.addWidget(
            make_muted_label(
                "בחר קובץ .tar מקומי — יועבר ל-Edge, יפורק ב-/opt/ras, "
                "ואז יורצו load-to-standalone.sh -l ו-edge_up."
            )
        )

        form = QFormLayout()
        self.host_edit = QLineEdit()
        self.user_edit = QLineEdit()
        self.password_edit = PasswordLineEdit()
        self._load_defaults()
        form.addRow("Host:", self.host_edit)
        form.addRow("User:", self.user_edit)
        form.addRow("Password:", self.password_edit)
        layout.addLayout(form)
        layout.addWidget(
            make_muted_label(
                "Password is not saved. Same password is used for SSH and remote sudo "
                "(load-to-standalone.sh)."
            )
        )

        file_row = QHBoxLayout()
        self.tar_label = make_muted_label("No tar file selected")
        self.browse_btn = make_secondary_button("Browse Tar…")
        self.browse_btn.clicked.connect(self._on_browse)
        file_row.addWidget(self.tar_label, stretch=1)
        file_row.addWidget(self.browse_btn)
        layout.addLayout(file_row)

        btn_row = QHBoxLayout()
        self.update_btn = make_primary_button("Update Edge")
        self.cancel_btn = make_secondary_button("Cancel")
        self.update_btn.clicked.connect(self._on_update)
        self.cancel_btn.clicked.connect(self._on_cancel)
        self.cancel_btn.setEnabled(False)
        btn_row.addWidget(self.update_btn)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        layout.addWidget(make_muted_label(f"Remote target: {EDGE_RAS_DIR}/<package>.tar"))

        self.progress_label = make_muted_label("Progress: idle")
        layout.addWidget(self.progress_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")
        layout.addWidget(self.progress_bar)

        self.log_view = make_log_view()
        layout.addWidget(self.log_view, stretch=1)

    def on_tab_shown(self) -> None:
        self._load_defaults()

    def is_busy(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def _load_defaults(self) -> None:
        drones = self.services.config.get("drones") or []
        if not drones:
            return
        d = drones[0]
        if not self.host_edit.text().strip():
            self.host_edit.setText(str(d.get("host", "")))
        if not self.user_edit.text().strip():
            self.user_edit.setText(str(d.get("user", "")))

    def _save_profile(self) -> None:
        host = self.host_edit.text().strip()
        user = self.user_edit.text().strip()
        if not host:
            return
        existing = (self.services.config.get("drones") or [{}])[0]
        self.services.config["drones"] = [
            {
                "name": host,
                "host": host,
                "user": user,
                "compose_path": existing.get("compose_path", "/opt/ras/docker-compose.yml"),
            }
        ]
        save_config(self.services.config)

    def _append_log(self, line: str) -> None:
        append_log_limited(self.log_view, line)

    def _set_progress(self, percent: int, label: str) -> None:
        self.progress_bar.setValue(max(0, min(100, percent)))
        self.progress_label.setText(f"Progress: {label}")

    def _on_browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Edge package",
            str(Path.home()),
            "Tar archives (*.tar)",
        )
        if not path:
            return
        self._tar_path = Path(path)
        self.tar_label.setText(str(self._tar_path))

    def _credentials(self) -> tuple[str, str, str] | None:
        host = self.host_edit.text().strip()
        user = self.user_edit.text().strip()
        password = self.password_edit.text()
        if not host or not user:
            QMessageBox.information(self, "Input Required", "Enter Edge host and user.")
            return None
        if not password:
            QMessageBox.information(self, "Input Required", "Enter the Edge SSH password.")
            return None
        return host, user, password

    def _on_update(self) -> None:
        if self.is_busy():
            return

        creds = self._credentials()
        if creds is None:
            return
        if self._tar_path is None or not self._tar_path.is_file():
            QMessageBox.information(self, "Input Required", "Select a local .tar package.")
            return
        if not self._tar_path.name.endswith(".tar"):
            QMessageBox.information(self, "Invalid File", "Package must be a .tar file.")
            return

        host, user, password = creds
        package_dir = self._tar_path.name[: -len(".tar")]
        if not confirm_action(
            self,
            "עדכון Edge",
            "האם לעדכן את Edge מהחבילה?\n\n"
            f"File: {self._tar_path.name}\n"
            f"Remote: {EDGE_RAS_DIR}/{self._tar_path.name}\n"
            f"Extract dir: {EDGE_RAS_DIR}/{package_dir}\n\n"
            "שלבים: upload → tar xvf → sudo load-to-standalone.sh -l → edge_up\n"
            "התהליך יכול לקחת זמן רב.",
        ):
            return

        self._save_profile()
        self.log_view.clear()
        self._set_progress(0, "Starting…")
        self._append_log(f"Starting Edge update: {self._tar_path.name}")
        self.update_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.browse_btn.setEnabled(False)
        self.host_edit.setEnabled(False)
        self.user_edit.setEnabled(False)
        self.password_edit.setEnabled(False)

        self._worker = EdgeDeployWorker(
            self.services.edge_deploy_runner,
            host,
            user,
            password,
            self._tar_path,
            parent=self,
        )
        self._worker.line.connect(self._log_bridge.line.emit)
        self._worker.progress.connect(self._set_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_cancel(self) -> None:
        self.services.edge_deploy_runner.cancel()
        self.cancel_btn.setEnabled(False)
        self._append_log("Cancel requested — will stop after the current step if possible.")
        self.progress_label.setText("Progress: cancelling…")

    def _on_finished(self, success: bool, message: str) -> None:
        self._worker = None
        self._append_log(message)
        if success:
            self._set_progress(100, "Done")
        else:
            self.progress_label.setText(f"Progress: failed — {message[:80]}")
        self.update_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.browse_btn.setEnabled(True)
        self.host_edit.setEnabled(True)
        self.user_edit.setEnabled(True)
        self.password_edit.setEnabled(True)
        if success:
            QMessageBox.information(self, "Edge Update", message)
        else:
            QMessageBox.warning(self, "Edge Update Failed", message)
