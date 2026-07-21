"""Main application window."""

from __future__ import annotations

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMainWindow

from nexus_toolkit.config import load_config
from nexus_toolkit.ui.jira_tab import JiraTab
from nexus_toolkit.ui.settings_dialog import SettingsDialog


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.config = load_config()
        self.setWindowTitle("Nexus Toolkit")
        self.resize(1100, 800)

        self.jira_tab = JiraTab(self.config)
        self.setCentralWidget(self.jira_tab)

        self._build_menu()

    def _build_menu(self) -> None:
        menu = self.menuBar().addMenu("File")
        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(self._open_settings)
        menu.addAction(settings_action)

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.close)
        menu.addAction(quit_action)

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.config, self)
        if dialog.exec():
            self.config = load_config()
