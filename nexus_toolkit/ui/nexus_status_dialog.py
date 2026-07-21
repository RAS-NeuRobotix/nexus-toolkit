"""Dialog for Nexus / Edge system status."""

from __future__ import annotations

from PyQt6.QtWidgets import QDialog, QTabWidget, QVBoxLayout

from nexus_toolkit.services.nexus_services import NexusServices
from nexus_toolkit.ui.design_system import STATUS_DIALOG_HEIGHT, STATUS_DIALOG_WIDTH
from nexus_toolkit.ui.edge_status_tab import EdgeStatusTab
from nexus_toolkit.ui.nexus_status_tab import NexusStatusTab
from nexus_toolkit.ui.widgets import add_dialog_footer, configure_task_dialog


class SystemStatusDialog(QDialog):
    def __init__(self, services: NexusServices, parent=None) -> None:
        super().__init__(parent)
        self.services = services
        configure_task_dialog(self, "System Status", STATUS_DIALOG_WIDTH, STATUS_DIALOG_HEIGHT)

        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        self.nexus_tab = NexusStatusTab(services, self)
        self.edge_tab = EdgeStatusTab(services, self)
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
