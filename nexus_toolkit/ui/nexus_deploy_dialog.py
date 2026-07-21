"""Dialog for updating Nexus / Edge systems."""

from __future__ import annotations

from PyQt6.QtWidgets import QDialog, QTabWidget, QVBoxLayout

from nexus_toolkit.services.nexus_services import NexusServices
from nexus_toolkit.ui.design_system import DIALOG_HEIGHT, DIALOG_WIDTH
from nexus_toolkit.ui.edge_deploy_tab import EdgeDeployTab
from nexus_toolkit.ui.nexus_deploy_tab import NexusDeployTab
from nexus_toolkit.ui.widgets import add_dialog_footer, configure_task_dialog


class DeployDialog(QDialog):
    def __init__(self, services: NexusServices, parent=None) -> None:
        super().__init__(parent)
        self.services = services
        configure_task_dialog(self, "Update System", DIALOG_WIDTH, DIALOG_HEIGHT + 40)

        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        self.nexus_tab = NexusDeployTab(services, self)
        self.edge_tab = EdgeDeployTab(services, self)
        self.tabs.addTab(self.nexus_tab, "Nexus")
        self.tabs.addTab(self.edge_tab, "Edge")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tabs)

        add_dialog_footer(layout, self)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._on_tab_changed(self.tabs.currentIndex())

    def _on_tab_changed(self, index: int) -> None:
        widget = self.tabs.widget(index)
        on_shown = getattr(widget, "on_tab_shown", None)
        if callable(on_shown):
            on_shown()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.edge_tab.is_busy():
            # Allow cancel request; keep dialog open if still busy after confirm style
            from nexus_toolkit.ui.widgets import confirm_action

            if not confirm_action(
                self,
                "עדכון Edge פעיל",
                "עדכון Edge עדיין רץ. לסגור בכל זאת?\n"
                "(הפעולה ברקע עלולה להמשיך עד סוף השלב הנוכחי)",
            ):
                event.ignore()
                return
            self.services.edge_deploy_runner.cancel()

        self.nexus_tab.stop_frontend_if_needed()
        super().closeEvent(event)
