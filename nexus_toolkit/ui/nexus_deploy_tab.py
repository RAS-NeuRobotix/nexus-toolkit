"""Nexus (cave) update tab — DeployManager + frontend dev."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from nexus_toolkit.config import save_config
from nexus_toolkit.paths import FRONTEND_APP_DIR
from nexus_toolkit.services.azure_auth import check_azure_login, start_az_login
from nexus_toolkit.services.nexus_services import NexusServices
from nexus_toolkit.services.sudo_auth import ensure_sudo_for_deploy, is_sudo_cached
from nexus_toolkit.ui.deploy_worker import DeployWorker
from nexus_toolkit.ui.front_dev_worker import FrontDevWorker
from nexus_toolkit.ui.log_view import LogBridge, append_log_limited
from nexus_toolkit.ui.widgets import (
    ask_password,
    confirm_action,
    make_danger_button,
    make_log_view,
    make_muted_label,
    make_primary_button,
    make_secondary_button,
    make_status_row,
    set_status_indicator,
)


class NexusDeployTab(QWidget):
    def __init__(self, services: NexusServices, parent=None) -> None:
        super().__init__(parent)
        self.services = services
        self._deploy_worker: DeployWorker | None = None
        self._front_worker: FrontDevWorker | None = None
        self._log_bridge = LogBridge()
        self._log_bridge.line.connect(self._append_deploy_log)

        layout = QVBoxLayout(self)

        azure_row = QHBoxLayout()
        self.azure_indicator, self.azure_status = make_status_row("Checking Azure...")
        azure_row.addWidget(self.azure_indicator)
        azure_row.addWidget(self.azure_status)
        azure_row.addStretch()
        azure_login_btn = make_secondary_button("Azure Login")
        azure_login_btn.clicked.connect(self._on_azure_login)
        azure_row.addWidget(azure_login_btn)
        layout.addLayout(azure_row)

        form = QFormLayout()
        deploy_cfg = self.services.config.setdefault("deploy", {})
        self.be_version = QLineEdit(str(deploy_cfg.get("be_version", "main")))
        self.fe_version = QLineEdit(str(deploy_cfg.get("fe_version", "latest")))
        self.project_version = QLineEdit(str(deploy_cfg.get("project") or ""))
        self.project_version.setPlaceholderText("Optional (e.g. Duchifat)")
        form.addRow("Backend version:", self.be_version)
        form.addRow("Frontend version:", self.fe_version)
        form.addRow("Project:", self.project_version)
        layout.addLayout(form)

        deploy_btn_row = QHBoxLayout()
        self.deploy_btn = make_primary_button("Update System (download + up)")
        self.deploy_btn.clicked.connect(self._on_deploy)
        self.cancel_deploy_btn = make_secondary_button("Cancel")
        self.cancel_deploy_btn.clicked.connect(self._on_cancel_deploy)
        self.cancel_deploy_btn.setEnabled(False)
        deploy_btn_row.addWidget(self.deploy_btn)
        deploy_btn_row.addWidget(self.cancel_deploy_btn)
        deploy_btn_row.addStretch()
        layout.addLayout(deploy_btn_row)

        front_btn_row = QHBoxLayout()
        self.front_start_btn = make_primary_button("Start Front (npm run dev)")
        self.front_stop_btn = make_danger_button("Stop Front")
        self.front_stop_btn.setEnabled(False)
        self.front_start_btn.clicked.connect(self._on_front_start)
        self.front_stop_btn.clicked.connect(self._on_front_stop)
        front_btn_row.addWidget(self.front_start_btn)
        front_btn_row.addWidget(self.front_stop_btn)
        front_btn_row.addStretch()
        layout.addLayout(front_btn_row)

        self.front_path_label = make_muted_label(f"Front directory: {self._frontend_dir()}")
        layout.addWidget(self.front_path_label)

        self.deploy_log = make_log_view()
        layout.addWidget(self.deploy_log, stretch=1)

        self.refresh_azure_status()
        self._sync_front_buttons()

    def on_tab_shown(self) -> None:
        self.refresh_azure_status()
        self._sync_front_buttons()

    def is_busy(self) -> bool:
        return (
            (self._deploy_worker is not None and self._deploy_worker.isRunning())
            or self.services.frontend_runner.running
            or (self._front_worker is not None and self._front_worker.isRunning())
        )

    def stop_frontend_if_needed(self) -> None:
        if self.services.frontend_runner.running and confirm_action(
            self,
            "פרונט פעיל",
            "שרת הפיתוח של הפרונט עדיין רץ. לעצור לפני סגירה?",
        ):
            self._on_front_stop()

    def _frontend_dir(self) -> Path:
        frontend_cfg = self.services.config.get("frontend") or {}
        configured = str(frontend_cfg.get("app_dir") or "").strip()
        if configured:
            return Path(configured).expanduser()
        return FRONTEND_APP_DIR

    def _sync_front_buttons(self) -> None:
        running = self.services.frontend_runner.running or (
            self._front_worker is not None and self._front_worker.isRunning()
        )
        self.front_start_btn.setEnabled(not running)
        self.front_stop_btn.setEnabled(running)

    def refresh_azure_status(self) -> None:
        ok, message = check_azure_login()
        set_status_indicator(self.azure_indicator, ok, message, self.azure_status)
        deploy_running = self._deploy_worker is not None and self._deploy_worker.isRunning()
        if not deploy_running:
            self.deploy_btn.setEnabled(ok)

    def _append_deploy_log(self, line: str) -> None:
        append_log_limited(self.deploy_log, line)

    def _on_azure_login(self) -> None:
        self._log_bridge.line.emit("Starting az login...")
        start_az_login(on_line=self._log_bridge.line.emit)
        QTimer.singleShot(5000, self.refresh_azure_status)

    def _on_front_start(self) -> None:
        if self._front_worker is not None and self._front_worker.isRunning():
            return

        app_dir = self._frontend_dir()
        self.front_path_label.setText(f"Front directory: {app_dir}")
        self._append_deploy_log("=== npm run dev ===")

        self._front_worker = FrontDevWorker(self.services.frontend_runner, app_dir, parent=self)
        self._front_worker.line.connect(self._log_bridge.line.emit)
        self._front_worker.finished.connect(self._on_front_finished)
        self._front_worker.start()
        self._sync_front_buttons()

    def _on_front_stop(self) -> None:
        if self._front_worker is not None and self._front_worker.isRunning():
            self._front_worker.requestInterruption()
        self.services.frontend_runner.stop()
        self._sync_front_buttons()
        self._append_deploy_log("Stopping frontend dev server...")

    def _on_front_finished(self, success: bool, message: str) -> None:
        self._append_deploy_log(message)
        self._sync_front_buttons()
        if not success and message != "Frontend dev server stopped":
            QMessageBox.warning(self, "Frontend Dev Server", message)

    def _on_deploy(self) -> None:
        if self._deploy_worker is not None and self._deploy_worker.isRunning():
            return

        self.refresh_azure_status()
        ok, _ = check_azure_login()
        if not ok:
            QMessageBox.warning(self, "Azure Required", "Log in to Azure before updating.")
            return

        if not confirm_action(
            self,
            "לפני העדכון",
            "במהלך העדכון DeployManager עוצר ומעלה מחדש את שירותי Nexus.\n\n"
            "מומלץ לסגור את אפליקציית Nexus לפני שממשיכים.\n"
            "העדכון עלול לקחת כמה דקות.\n\n"
            "להמשיך?",
        ):
            return

        deploy_cfg = self.services.config.setdefault("deploy", {})
        be = self.be_version.text().strip() or "main"
        fe = self.fe_version.text().strip() or "latest"
        project = self.project_version.text().strip() or None
        deploy_cfg.update({"be_version": be, "fe_version": fe, "project": project})
        save_config(self.services.config)

        self.deploy_log.clear()
        if not self._ensure_sudo_access():
            return

        self.deploy_btn.setEnabled(False)
        self.cancel_deploy_btn.setEnabled(True)

        self._deploy_worker = DeployWorker(
            self.services.deploy_runner,
            be,
            fe,
            project,
            parent=self,
        )
        self._deploy_worker.line.connect(self._append_deploy_log)
        self._deploy_worker.finished.connect(self._on_deploy_finished)
        self._deploy_worker.start()

    def _on_deploy_finished(self, success: bool, message: str) -> None:
        self._deploy_worker = None
        self._append_deploy_log(message)
        self.deploy_btn.setEnabled(True)
        self.cancel_deploy_btn.setEnabled(False)
        self.refresh_azure_status()
        if not success:
            QMessageBox.warning(self, "Deploy Failed", message)

    def _ensure_sudo_access(self) -> bool:
        password = None
        if not is_sudo_cached():
            entered, ok = ask_password(
                self,
                "נדרשת הרשאת מנהל",
                "העדכון דורש sudo (למשל chown על /opt/ras/app).\n"
                "הזן את סיסמת המשתמש:",
            )
            if not ok or not entered.strip():
                self._append_deploy_log("Deploy cancelled: sudo password required.")
                return False
            password = entered.strip()

        self._append_deploy_log("=== Preparing permissions ===")
        sudo_ok, sudo_msg = ensure_sudo_for_deploy(password)
        self._append_deploy_log(sudo_msg)
        if not sudo_ok:
            QMessageBox.warning(self, "Sudo Required", sudo_msg)
            return False
        return True

    def _on_cancel_deploy(self) -> None:
        self.services.deploy_runner.cancel()
        self.cancel_deploy_btn.setEnabled(False)
