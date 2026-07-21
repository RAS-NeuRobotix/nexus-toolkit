"""Main tab — launcher for Jira and Nexus Control dialogs."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from nexus_toolkit.models import BugDraft
from nexus_toolkit.services.nexus_services import NexusServices
from nexus_toolkit.ui.design_system import SPACING_MD, SPACING_SM
from nexus_toolkit.ui.jira_create_dialog import BugCreateDialog
from nexus_toolkit.ui.jira_search_dialog import BugSearchDialog
from nexus_toolkit.ui.nexus_deploy_dialog import DeployDialog
from nexus_toolkit.ui.nexus_local_logs_dialog import LocalLogsDialog
from nexus_toolkit.ui.nexus_status_dialog import SystemStatusDialog
from nexus_toolkit.ui.nexus_tests_dialog import NexusTestsDialog
from nexus_toolkit.ui.widgets import (
    make_launcher_button,
    make_page_title,
    make_section_title,
    make_subtitle,
)


class JiraTab(QWidget):
    def __init__(self, config: dict, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.nexus_services = NexusServices(config, on_recording_changed=self.refresh_recording_state)

        self._search_dialog: BugSearchDialog | None = None
        self._create_dialog: BugCreateDialog | None = None
        self._status_dialog: SystemStatusDialog | None = None
        self._deploy_dialog: DeployDialog | None = None
        self._local_logs_dialog: LocalLogsDialog | None = None
        self._tests_dialog: NexusTestsDialog | None = None

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        layout.setSpacing(SPACING_SM)

        layout.addWidget(make_page_title("Nexus Toolkit"))
        layout.addWidget(make_subtitle("בחר פעולה — כל פעולה נפתחת בחלון נפרד"))

        layout.addWidget(make_section_title("Jira"))

        search_btn = make_launcher_button("חיפוש באג קיים", "Search Existing Bug")
        search_btn.clicked.connect(self._open_search)
        layout.addWidget(search_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        create_btn = make_launcher_button("יצירת באג חדש", "Create New Bug")
        create_btn.clicked.connect(self._open_create)
        layout.addWidget(create_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addSpacing(SPACING_MD)
        layout.addWidget(make_section_title("Nexus Control"))

        for hebrew, english, handler in (
            ("סטטוס מערכת", "System Status", self._open_status),
            ("עדכון מערכת", "Update Nexus System", self._open_deploy),
            ("הקלטת לוגים", "Record Logs (local + drone)", self._open_local_logs),
            ("הרצת טסטים", "Run Automated Tests", self._open_tests),
        ):
            btn = make_launcher_button(hebrew, english)
            btn.clicked.connect(handler)
            layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addStretch()

    def refresh_recording_state(self) -> None:
        if self._create_dialog and self._create_dialog.isVisible():
            self._create_dialog._update_log_controls()

    def open_create_from_logs(
        self,
        *,
        description: str = "",
        draft: BugDraft | None = None,
        log_dir: Path | None = None,
    ) -> None:
        """Open Create Bug prefilled from a log investigation."""
        if self._create_dialog is None:
            self._create_dialog = BugCreateDialog(self.config, self)
        self._create_dialog.prefill(
            description=description,
            draft=draft,
            log_dir=log_dir,
            analyze_logs=False,
            attach_logs=True,
        )
        self._create_dialog.show()
        self._create_dialog.raise_()
        self._create_dialog.activateWindow()

    def _show_dialog(self, attr: str, factory) -> None:
        dialog = getattr(self, attr)
        if dialog is None:
            dialog = factory()
            setattr(self, attr, dialog)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _open_search(self) -> None:
        self._show_dialog("_search_dialog", lambda: BugSearchDialog(self.config, self))

    def _open_create(self) -> None:
        if self._create_dialog is None:
            self._create_dialog = BugCreateDialog(self.config, self)
        self._create_dialog._update_log_controls()
        self._create_dialog.show()
        self._create_dialog.raise_()
        self._create_dialog.activateWindow()

    def _open_status(self) -> None:
        self._show_dialog("_status_dialog", lambda: SystemStatusDialog(self.nexus_services, self))

    def _open_deploy(self) -> None:
        self._show_dialog("_deploy_dialog", lambda: DeployDialog(self.nexus_services, self))

    def _open_local_logs(self) -> None:
        self._show_dialog("_local_logs_dialog", lambda: LocalLogsDialog(self.nexus_services, self))

    def _open_tests(self) -> None:
        self._show_dialog("_tests_dialog", lambda: NexusTestsDialog(self.nexus_services, self))
