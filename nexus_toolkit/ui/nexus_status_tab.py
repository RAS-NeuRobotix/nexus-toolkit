"""Nexus (local cave) status panel for System Status dialog."""

from __future__ import annotations

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from nexus_toolkit.paths import NEXUS_DB_FILE
from nexus_toolkit.services.container_control import ContainerAction
from nexus_toolkit.services.deploy import check_docker
from nexus_toolkit.services.nexus_services import NexusServices
from nexus_toolkit.services.sudo_auth import is_sudo_cached
from nexus_toolkit.services.version_info import ContainerInfo
from nexus_toolkit.ui.container_action_worker import ContainerActionWorker
from nexus_toolkit.ui.database_reset_worker import DatabaseResetWorker
from nexus_toolkit.ui.design_system import COLOR_WARNING, STATUS_TABLE_ROW_HEIGHT
from nexus_toolkit.ui.status_refresh_worker import StatusRefreshWorker
from nexus_toolkit.ui.styles import STATUS_ERROR, STATUS_OK
from nexus_toolkit.ui.widgets import (
    ask_password,
    configure_status_table,
    confirm_action,
    make_compact_button,
    make_danger_button,
    make_muted_label,
    make_secondary_button,
    make_status_row,
    set_status_indicator,
)
from nexus_toolkit.utils import split_image_version_signature


class NexusStatusTab(QWidget):
    def __init__(self, services: NexusServices, parent=None) -> None:
        super().__init__(parent)
        self.services = services
        self._action_worker: ContainerActionWorker | None = None
        self._refresh_worker: StatusRefreshWorker | None = None
        self._db_worker: DatabaseResetWorker | None = None

        layout = QVBoxLayout(self)

        azure_row = QHBoxLayout()
        self.azure_indicator, self.azure_status = make_status_row("Checking Azure...")
        azure_row.addWidget(self.azure_indicator)
        azure_row.addWidget(self.azure_status)
        azure_row.addStretch()
        layout.addLayout(azure_row)

        version_header = QHBoxLayout()
        version_header.addWidget(QLabel("Installed Versions:"))
        version_header.addStretch()
        self.refresh_btn = make_secondary_button("Refresh")
        self.refresh_btn.clicked.connect(self.start_refresh)
        version_header.addWidget(self.refresh_btn)
        layout.addLayout(version_header)

        bulk_row = QHBoxLayout()
        self.stop_all_btn = make_danger_button("Stop All")
        self.start_all_btn = make_secondary_button("Start All")
        self.restart_all_btn = make_secondary_button("Restart All")
        self.delete_db_btn = make_danger_button("Delete Database")
        self.stop_all_btn.clicked.connect(lambda: self._run_all_action("stop"))
        self.start_all_btn.clicked.connect(lambda: self._run_all_action("start"))
        self.restart_all_btn.clicked.connect(lambda: self._run_all_action("restart"))
        self.delete_db_btn.clicked.connect(self._on_delete_database)
        bulk_row.addWidget(self.stop_all_btn)
        bulk_row.addWidget(self.start_all_btn)
        bulk_row.addWidget(self.restart_all_btn)
        bulk_row.addWidget(self.delete_db_btn)
        bulk_row.addStretch()
        layout.addLayout(bulk_row)

        layout.addWidget(
            make_muted_label(
                f"Delete Database: Stop All → delete {NEXUS_DB_FILE} → Start All (requires sudo)."
            )
        )

        self.version_table = QTableWidget(0, 5)
        self.version_table.setHorizontalHeaderLabels(
            ["Container", "Version", "Signature", "Status", "Actions"]
        )
        configure_status_table(self.version_table)
        layout.addWidget(self.version_table)

        self.action_status = make_muted_label("")
        layout.addWidget(self.action_status)

        self._set_refreshing(True)
        QTimer.singleShot(0, self._check_prerequisites)

    def on_tab_shown(self) -> None:
        self.start_refresh()

    def _action_busy(self) -> bool:
        return (
            (self._action_worker is not None and self._action_worker.isRunning())
            or (self._db_worker is not None and self._db_worker.isRunning())
        )

    def start_refresh(self) -> None:
        if self._refresh_worker is not None and self._refresh_worker.isRunning():
            return
        if self._action_busy():
            return

        self._set_refreshing(True)
        self._refresh_worker = StatusRefreshWorker(parent=self)
        self._refresh_worker.finished.connect(self._on_refresh_finished)
        self._refresh_worker.start()

    def _set_refreshing(self, refreshing: bool) -> None:
        self.refresh_btn.setEnabled(not refreshing)
        if refreshing:
            self.azure_status.setText("Checking Azure...")
            self.azure_indicator.setStyleSheet(f"color: {COLOR_WARNING}; font-size: 16px;")

    def _on_refresh_finished(self, azure_ok: bool, azure_message: str, versions: list) -> None:
        set_status_indicator(self.azure_indicator, azure_ok, azure_message, self.azure_status)
        self._apply_versions(versions)
        actions_busy = self._action_busy()
        self.refresh_btn.setEnabled(not actions_busy)
        self.stop_all_btn.setEnabled(not actions_busy)
        self.start_all_btn.setEnabled(not actions_busy)
        self.restart_all_btn.setEnabled(not actions_busy)
        self.delete_db_btn.setEnabled(not actions_busy)

    def _apply_versions(self, infos: list[ContainerInfo]) -> None:
        self.version_table.setRowCount(len(infos))
        for row, info in enumerate(infos):
            self.version_table.setRowHeight(row, STATUS_TABLE_ROW_HEIGHT)
            version, signature = split_image_version_signature(info.image)
            self.version_table.setItem(row, 0, QTableWidgetItem(info.name))
            self.version_table.setItem(row, 1, QTableWidgetItem(version))
            self.version_table.setItem(row, 2, QTableWidgetItem(signature))
            status_item = QTableWidgetItem(info.status)
            status_item.setForeground(QColor(STATUS_OK if info.running else STATUS_ERROR))
            self.version_table.setItem(row, 3, status_item)
            self.version_table.setCellWidget(row, 4, self._make_action_buttons(info.service))

    def _make_action_buttons(self, service: str) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(6, 4, 8, 4)
        layout.setSpacing(6)

        down_btn = make_compact_button("Down")
        up_btn = make_compact_button("Up")
        restart_btn = make_compact_button("Restart", wide=True)

        down_btn.clicked.connect(lambda: self._run_action(service, "stop"))
        up_btn.clicked.connect(lambda: self._run_action(service, "start"))
        restart_btn.clicked.connect(lambda: self._run_action(service, "restart"))

        layout.addWidget(down_btn)
        layout.addWidget(up_btn)
        layout.addWidget(restart_btn)
        return widget

    def _set_actions_enabled(self, enabled: bool) -> None:
        self.refresh_btn.setEnabled(enabled)
        self.stop_all_btn.setEnabled(enabled)
        self.start_all_btn.setEnabled(enabled)
        self.restart_all_btn.setEnabled(enabled)
        self.delete_db_btn.setEnabled(enabled)
        for row in range(self.version_table.rowCount()):
            widget = self.version_table.cellWidget(row, 4)
            if widget is None:
                continue
            for btn in widget.findChildren(QPushButton):
                btn.setEnabled(enabled)

    def _run_action(self, service: str, action: ContainerAction) -> None:
        if self._action_busy():
            return

        self._set_actions_enabled(False)
        self._action_worker = ContainerActionWorker(action, service=service, parent=self)
        self._action_worker.finished.connect(self._on_action_finished)
        self._action_worker.start()

    def _run_all_action(self, action: ContainerAction) -> None:
        if self._action_busy():
            return

        if action == "stop" and not confirm_action(
            self,
            "אישור פעולה",
            "האם לעצור את כל שירותי Nexus?",
        ):
            return
        if action == "restart" and not confirm_action(
            self,
            "אישור פעולה",
            "האם להפעיל מחדש את כל שירותי Nexus?",
        ):
            return

        self._set_actions_enabled(False)
        self._action_worker = ContainerActionWorker(action, service=None, parent=self)
        self._action_worker.finished.connect(self._on_action_finished)
        self._action_worker.start()

    def _on_action_finished(self, success: bool, message: str) -> None:
        self._set_actions_enabled(True)
        self.start_refresh()
        if not success:
            QMessageBox.warning(self, "Container Action Failed", message)

    def _on_delete_database(self) -> None:
        if self._action_busy():
            return

        if not confirm_action(
            self,
            "מחיקת דאטה בייס",
            "האם אתה בטוח שאתה רוצה למחוק את הדאטה בייס?\n\n"
            f"הקובץ יימחק:\n{NEXUS_DB_FILE}\n\n"
            "המערכת תיעצר, הדאטה בייס יימחק, ואז המערכת תופעל מחדש.\n"
            "פעולה זו בלתי הפיכה.",
        ):
            return

        password: str | None = None
        if not is_sudo_cached():
            entered, ok = ask_password(
                self,
                "נדרשת הרשאת מנהל",
                f"מחיקת הדאטה בייס דורשת sudo:\n{NEXUS_DB_FILE}\n\n"
                "הזן את סיסמת המשתמש:",
            )
            if not ok or not entered.strip():
                self.action_status.setText("Delete Database cancelled: sudo password required.")
                return
            password = entered.strip()

        self.action_status.setText("Deleting database...")
        self._set_actions_enabled(False)
        self._db_worker = DatabaseResetWorker(password=password, parent=self)
        self._db_worker.line.connect(self.action_status.setText)
        self._db_worker.finished.connect(self._on_delete_database_finished)
        self._db_worker.start()

    def _on_delete_database_finished(self, success: bool, message: str) -> None:
        self.action_status.setText(message)
        self._set_actions_enabled(True)
        self.start_refresh()
        if success:
            QMessageBox.information(self, "Database Deleted", message)
        else:
            QMessageBox.warning(self, "Delete Database Failed", message)

    def _check_prerequisites(self) -> None:
        docker_ok, docker_msg = check_docker()
        if not docker_ok:
            QMessageBox.warning(self, "Docker", docker_msg)
