"""Edge (drone) status panel — SSH compose control."""

from __future__ import annotations

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from nexus_toolkit.config import save_config
from nexus_toolkit.services.container_control import ContainerAction
from nexus_toolkit.services.edge_control import DEFAULT_EDGE_COMPOSE, EdgeContainerInfo
from nexus_toolkit.services.nexus_services import NexusServices
from nexus_toolkit.ui.design_system import COLOR_WARNING, SPACING_LG, STATUS_TABLE_ROW_HEIGHT
from nexus_toolkit.ui.edge_workers import EdgeActionWorker, EdgeConnectWorker, EdgeRefreshWorker
from nexus_toolkit.ui.styles import STATUS_ERROR, STATUS_OK
from nexus_toolkit.ui.widgets import (
    PasswordLineEdit,
    configure_status_table,
    confirm_action,
    make_compact_button,
    make_danger_button,
    make_muted_label,
    make_primary_button,
    make_secondary_button,
    make_status_row,
    set_status_indicator,
)
from nexus_toolkit.utils import split_image_version_signature


class EdgeStatusTab(QWidget):
    def __init__(self, services: NexusServices, parent=None) -> None:
        super().__init__(parent)
        self.services = services
        self._connected = False
        self._password = ""
        self._connect_worker: EdgeConnectWorker | None = None
        self._refresh_worker: EdgeRefreshWorker | None = None
        self._action_worker: EdgeActionWorker | None = None
        self._edge_visited = False

        layout = QVBoxLayout(self)

        layout.addWidget(
            make_muted_label(
                "התחבר ל-Edge (רחפן) ב-SSH כדי לראות ולשלוט בשירותי docker compose."
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
        layout.addWidget(make_muted_label("Password is not saved — enter it each session."))

        conn_row = QHBoxLayout()
        self.connect_indicator, self.connect_status = make_status_row("Not connected")
        set_status_indicator(self.connect_indicator, False, "Not connected", self.connect_status)
        conn_row.addWidget(self.connect_indicator)
        conn_row.addWidget(self.connect_status)
        conn_row.addStretch()
        layout.addLayout(conn_row)

        btn_row = QHBoxLayout()
        self.connect_btn = make_primary_button("Connect")
        self.disconnect_btn = make_secondary_button("Disconnect")
        self.refresh_btn = make_secondary_button("Refresh")
        self.stop_all_btn = make_danger_button("Stop All")
        self.start_all_btn = make_secondary_button("Start All")
        self.restart_all_btn = make_secondary_button("Restart All")
        self.connect_btn.clicked.connect(self._on_connect)
        self.disconnect_btn.clicked.connect(self._on_disconnect)
        self.refresh_btn.clicked.connect(self._on_refresh)
        self.stop_all_btn.clicked.connect(lambda: self._run_all_action("stop"))
        self.start_all_btn.clicked.connect(lambda: self._run_all_action("start"))
        self.restart_all_btn.clicked.connect(lambda: self._run_all_action("restart"))
        self.disconnect_btn.setEnabled(False)
        self.refresh_btn.setEnabled(False)
        btn_row.addWidget(self.connect_btn)
        btn_row.addWidget(self.disconnect_btn)
        btn_row.addWidget(self.refresh_btn)
        btn_row.addSpacing(SPACING_LG)
        btn_row.addWidget(self.stop_all_btn)
        btn_row.addWidget(self.start_all_btn)
        btn_row.addWidget(self.restart_all_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.version_table = QTableWidget(0, 5)
        self.version_table.setHorizontalHeaderLabels(
            ["Container", "Version", "Signature", "Status", "Actions"]
        )
        configure_status_table(self.version_table)
        layout.addWidget(self.version_table)

        self.action_status = make_muted_label("Connect to Edge to load compose services.")
        layout.addWidget(self.action_status)

        self._set_controls_connected(False)

    def on_tab_shown(self) -> None:
        if not self._edge_visited:
            self._edge_visited = True
            self.action_status.setText("הזן פרטי חיבור ולחץ Connect.")
        if self._connected and not self._action_busy():
            self._on_refresh()

    def _load_defaults(self) -> None:
        drones = self.services.config.get("drones") or []
        if drones:
            d = drones[0]
            self.host_edit.setText(str(d.get("host", "")))
            self.user_edit.setText(str(d.get("user", "")))

    def _save_profile(self) -> None:
        host = self.host_edit.text().strip()
        user = self.user_edit.text().strip()
        if not host:
            return
        self.services.config["drones"] = [
            {
                "name": host,
                "host": host,
                "user": user,
                "compose_path": DEFAULT_EDGE_COMPOSE,
            }
        ]
        save_config(self.services.config)

    def _credentials(self) -> tuple[str, str, str, str] | None:
        host = self.host_edit.text().strip()
        user = self.user_edit.text().strip()
        password = self.password_edit.text() or self._password
        if not host or not user:
            QMessageBox.information(self, "Input Required", "Enter Edge host and user.")
            return None
        if not password:
            QMessageBox.information(self, "Input Required", "Enter the Edge SSH password.")
            return None
        return host, user, password, DEFAULT_EDGE_COMPOSE

    def _action_busy(self) -> bool:
        return (
            (self._connect_worker is not None and self._connect_worker.isRunning())
            or (self._refresh_worker is not None and self._refresh_worker.isRunning())
            or (self._action_worker is not None and self._action_worker.isRunning())
        )

    def _set_controls_connected(self, connected: bool) -> None:
        self._connected = connected
        self.disconnect_btn.setEnabled(connected and not self._action_busy())
        self.refresh_btn.setEnabled(connected and not self._action_busy())
        self.stop_all_btn.setEnabled(connected and not self._action_busy())
        self.start_all_btn.setEnabled(connected and not self._action_busy())
        self.restart_all_btn.setEnabled(connected and not self._action_busy())
        self.connect_btn.setEnabled(not self._action_busy())
        for row in range(self.version_table.rowCount()):
            widget = self.version_table.cellWidget(row, 4)
            if widget is None:
                continue
            for btn in widget.findChildren(QPushButton):
                btn.setEnabled(connected and not self._action_busy())

    def _set_busy(self, busy: bool) -> None:
        self.connect_btn.setEnabled(not busy)
        self.disconnect_btn.setEnabled(self._connected and not busy)
        self.refresh_btn.setEnabled(self._connected and not busy)
        self.stop_all_btn.setEnabled(self._connected and not busy)
        self.start_all_btn.setEnabled(self._connected and not busy)
        self.restart_all_btn.setEnabled(self._connected and not busy)
        self.host_edit.setEnabled(not busy)
        self.user_edit.setEnabled(not busy)
        self.password_edit.setEnabled(not busy)
        for row in range(self.version_table.rowCount()):
            widget = self.version_table.cellWidget(row, 4)
            if widget is None:
                continue
            for btn in widget.findChildren(QPushButton):
                btn.setEnabled(self._connected and not busy)

    def _on_connect(self) -> None:
        if self._action_busy():
            return
        creds = self._credentials()
        if creds is None:
            return
        host, user, password, compose = creds

        self.action_status.setText("Connecting to Edge...")
        self.connect_status.setText("Connecting...")
        self.connect_indicator.setStyleSheet(f"color: {COLOR_WARNING}; font-size: 16px;")
        self._set_busy(True)

        self._connect_worker = EdgeConnectWorker(host, user, password, compose, parent=self)
        self._connect_worker.finished.connect(self._on_connect_finished)
        self._connect_worker.start()

    def _on_connect_finished(self, ok: bool, message: str, infos: list) -> None:
        self._connect_worker = None
        if not ok:
            self._password = ""
            self._connected = False
            set_status_indicator(self.connect_indicator, False, "Not connected", self.connect_status)
            self.action_status.setText(message)
            self.version_table.setRowCount(0)
            self._set_busy(False)
            self._set_controls_connected(False)
            QMessageBox.warning(self, "Edge Connection Failed", message)
            return

        creds = self._credentials()
        if creds:
            _, _, password, _ = creds
            self._password = password
        self._save_profile()
        set_status_indicator(self.connect_indicator, True, message, self.connect_status)
        self.action_status.setText(message)
        self._apply_versions(infos)
        self._set_busy(False)
        self._set_controls_connected(True)

    def _on_disconnect(self) -> None:
        if self._action_busy():
            return
        self._password = ""
        self._connected = False
        self.version_table.setRowCount(0)
        set_status_indicator(self.connect_indicator, False, "Not connected", self.connect_status)
        self.action_status.setText("Disconnected from Edge.")
        self._set_controls_connected(False)

    def _on_refresh(self) -> None:
        if not self._connected or self._action_busy():
            return
        creds = self._credentials()
        if creds is None:
            return
        host, user, password, compose = creds
        self.action_status.setText("Refreshing Edge status...")
        self._set_busy(True)
        self._refresh_worker = EdgeRefreshWorker(host, user, password, compose, parent=self)
        self._refresh_worker.finished.connect(self._on_refresh_finished)
        self._refresh_worker.start()

    def _on_refresh_finished(self, ok: bool, message: str, infos: list) -> None:
        self._refresh_worker = None
        self._set_busy(False)
        self._set_controls_connected(self._connected)
        if not ok:
            self.action_status.setText(message)
            QMessageBox.warning(self, "Edge Refresh Failed", message)
            return
        self.action_status.setText(message)
        self._apply_versions(infos)

    def _apply_versions(self, infos: list[EdgeContainerInfo]) -> None:
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

    def _run_action(self, service: str, action: ContainerAction) -> None:
        if not self._connected or self._action_busy():
            return
        creds = self._credentials()
        if creds is None:
            return
        host, user, password, compose = creds

        self.action_status.setText(f"{action} {service}...")
        self._set_busy(True)
        self._action_worker = EdgeActionWorker(
            host, user, password, compose, action, service=service, parent=self
        )
        self._action_worker.finished.connect(self._on_action_finished)
        self._action_worker.start()

    def _run_all_action(self, action: ContainerAction) -> None:
        if not self._connected or self._action_busy():
            return

        if action == "stop" and not confirm_action(
            self,
            "אישור פעולה",
            "האם לעצור את כל שירותי Edge?",
        ):
            return
        if action == "restart" and not confirm_action(
            self,
            "אישור פעולה",
            "האם להפעיל מחדש את כל שירותי Edge?",
        ):
            return

        creds = self._credentials()
        if creds is None:
            return
        host, user, password, compose = creds

        self.action_status.setText(f"{action} all Edge services...")
        self._set_busy(True)
        self._action_worker = EdgeActionWorker(
            host, user, password, compose, action, service=None, parent=self
        )
        self._action_worker.finished.connect(self._on_action_finished)
        self._action_worker.start()

    def _on_action_finished(self, success: bool, message: str) -> None:
        self._action_worker = None
        self.action_status.setText(message)
        self._set_busy(False)
        self._set_controls_connected(self._connected)
        if not success:
            QMessageBox.warning(self, "Edge Action Failed", message)
        if self._connected:
            self._on_refresh()
