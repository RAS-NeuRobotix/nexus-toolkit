"""Dialog for selecting and running Nexus automated tests."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QBrush, QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from nexus_toolkit.config import save_config
from nexus_toolkit.paths import resolve_frontend_app_dir
from nexus_toolkit.services.nexus_services import NexusServices
from nexus_toolkit.services.nexus_tests import (
    DEFAULT_NEXUS_TESTS_DIR,
    DEFAULT_NEXUS_TESTS_GIT,
    DEFAULT_VITE_URL,
    SUITE_PRESETS,
    CollectedTest,
    TestRunOptions,
    TestRunSummary,
    allure_dirs,
    check_vite_running,
    ensure_repo_dir,
    list_allure_archives,
    open_allure_report,
    parse_test_display,
)
from nexus_toolkit.ui.design_system import (
    COLOR_ERROR,
    COLOR_MUTED,
    COLOR_SUCCESS,
    COLOR_TEXT,
    COLOR_TEXT_SOFT,
    COLOR_WARNING,
    SPACING_LG,
    SPACING_MD,
    SPACING_SM,
)
from nexus_toolkit.ui.front_dev_worker import FrontDevWorker
from nexus_toolkit.ui.log_view import LogBridge, append_log_limited
from nexus_toolkit.ui.nexus_tests_worker import TestsCollectWorker, TestsGitWorker, TestsRunWorker
from nexus_toolkit.ui.widgets import (
    add_dialog_footer,
    make_log_view,
    make_muted_label,
    make_primary_button,
    make_secondary_button,
)


class NexusTestsDialog(QDialog):
    def __init__(self, services: NexusServices, parent=None) -> None:
        super().__init__(parent)
        self.services = services
        self._git_worker: TestsGitWorker | None = None
        self._collect_worker: TestsCollectWorker | None = None
        self._run_worker: TestsRunWorker | None = None
        self._front_worker: FrontDevWorker | None = None
        self._nodeids: list[str] = []
        self._descriptions: dict[str, str] = {}
        self._last_summary: TestRunSummary | None = None
        self._updating_checks = False
        self._geometry_applied = False
        self._log_bridge = LogBridge()

        self.setWindowTitle("Run Automated Tests")
        self.setMinimumSize(1100, 780)

        tests_cfg = self.services.config.setdefault("tests", {})
        layout = QVBoxLayout(self)
        layout.setSpacing(SPACING_MD)
        layout.setContentsMargins(SPACING_MD, SPACING_MD, SPACING_MD, SPACING_MD)

        layout.addWidget(
            make_muted_label(
                "כתום = טסט נוכחי → כפתור Run This (בלי ✓). "
                "✓ + Run Checked = כמה טסטים. לחיצה כפולה = הרצה מיידית."
            )
        )

        # --- Repository ---
        layout.addWidget(_section_title("Repository"))
        path_row = QHBoxLayout()
        path_row.setSpacing(SPACING_SM)
        self.repo_edit = QLineEdit(str(tests_cfg.get("repo_dir") or DEFAULT_NEXUS_TESTS_DIR))
        browse_btn = make_secondary_button("Browse…")
        browse_btn.clicked.connect(self._on_browse_repo)
        self.git_btn = make_secondary_button("Clone / Update from Git")
        self.git_btn.clicked.connect(self._on_git_update)
        path_row.addWidget(QLabel("Repo:"))
        path_row.addWidget(self.repo_edit, stretch=1)
        path_row.addWidget(browse_btn)
        path_row.addWidget(self.git_btn)
        layout.addLayout(path_row)

        git_row = QHBoxLayout()
        git_row.setSpacing(SPACING_SM)
        self.git_url_edit = QLineEdit(str(tests_cfg.get("git_url") or DEFAULT_NEXUS_TESTS_GIT))
        git_row.addWidget(QLabel("Git URL:"))
        git_row.addWidget(self.git_url_edit, stretch=1)
        layout.addLayout(git_row)

        # --- Suite & Options (fixed height — must not be crushed by splitter) ---
        layout.addWidget(_section_title("Suite & Options"))
        suite_row = QHBoxLayout()
        suite_row.setSpacing(SPACING_SM)
        self.suite_combo = QComboBox()
        for name in SUITE_PRESETS:
            self.suite_combo.addItem(name)
        self.suite_combo.setMinimumWidth(180)
        self.refresh_btn = make_secondary_button("Refresh Test List")
        self.refresh_btn.clicked.connect(self._on_refresh_list)
        suite_row.addWidget(QLabel("Suite:"))
        suite_row.addWidget(self.suite_combo)
        suite_row.addWidget(self.refresh_btn)
        suite_row.addStretch()
        layout.addLayout(suite_row)

        self.headless_cb = QCheckBox("Headless")
        self.headless_cb.setChecked(True)
        self.headless_cb.setToolTip("Run browser without UI (HEADLESS=true)")
        self.parallel_cb = QCheckBox("Parallel")
        self.parallel_cb.setChecked(False)
        self.parallel_workers = QSpinBox()
        self.parallel_workers.setRange(1, 16)
        self.parallel_workers.setValue(2)
        self.parallel_workers.setEnabled(False)
        self.parallel_cb.toggled.connect(self.parallel_workers.setEnabled)

        self.allure_cb = QCheckBox("Allure")
        self.allure_cb.setChecked(False)
        self.allure_cb.setToolTip("Generate Allure report + keep last 20 runs")
        self.drone_cb = QCheckBox("Drone tests")
        self.drone_cb.setChecked(True)
        self.drone_cb.setToolTip("--drone=True")
        self.lab_cb = QCheckBox("Lab tests")
        self.lab_cb.setChecked(False)
        self.lab_cb.setToolTip("--lab=true")
        self.flight_cb = QCheckBox("Flight only")
        self.flight_cb.setChecked(False)
        self.flight_cb.setToolTip("Filter to @pytest.mark.flight")

        self.reruns_spin = QSpinBox()
        self.reruns_spin.setRange(0, 5)
        self.reruns_spin.setValue(1)
        self.reruns_spin.setMinimumWidth(72)
        self.browser_combo = QComboBox()
        self.browser_combo.addItems(["chromium", "firefox", "webkit"])
        self.browser_combo.setMinimumWidth(120)

        options_host = QWidget()
        options_host.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        options_grid = QGridLayout(options_host)
        options_grid.setContentsMargins(0, 0, 0, 0)
        options_grid.setHorizontalSpacing(SPACING_LG)
        options_grid.setVerticalSpacing(SPACING_MD)
        options_grid.addWidget(self.headless_cb, 0, 0)
        parallel_wrap = QHBoxLayout()
        parallel_wrap.setSpacing(SPACING_SM)
        parallel_wrap.addWidget(self.parallel_cb)
        parallel_wrap.addWidget(QLabel("workers:"))
        parallel_wrap.addWidget(self.parallel_workers)
        parallel_wrap.addStretch()
        parallel_w = QWidget()
        parallel_w.setLayout(parallel_wrap)
        options_grid.addWidget(parallel_w, 0, 1)

        options_grid.addWidget(self.allure_cb, 1, 0)
        options_grid.addWidget(self.drone_cb, 1, 1)
        options_grid.addWidget(self.lab_cb, 2, 0)
        options_grid.addWidget(self.flight_cb, 2, 1)

        rerun_row = QHBoxLayout()
        rerun_row.setSpacing(SPACING_SM)
        rerun_row.addWidget(QLabel("Reruns:"))
        rerun_row.addWidget(self.reruns_spin)
        rerun_row.addStretch()
        rerun_w = QWidget()
        rerun_w.setLayout(rerun_row)
        options_grid.addWidget(rerun_w, 3, 0)

        browser_row = QHBoxLayout()
        browser_row.setSpacing(SPACING_SM)
        browser_row.addWidget(QLabel("Browser:"))
        browser_row.addWidget(self.browser_combo)
        browser_row.addStretch()
        browser_w = QWidget()
        browser_w.setLayout(browser_row)
        options_grid.addWidget(browser_w, 3, 1)
        layout.addWidget(options_host)

        # --- Tests ---
        layout.addWidget(_section_title("Tests"))
        select_row = QHBoxLayout()
        select_row.setSpacing(SPACING_SM)
        select_all_btn = make_secondary_button("Select All")
        select_none_btn = make_secondary_button("Select None")
        select_all_btn.clicked.connect(self._select_all)
        select_none_btn.clicked.connect(self._select_none)
        self.list_status = make_muted_label("לחץ Refresh Test List כדי לטעון טסטים.")
        select_row.addWidget(select_all_btn)
        select_row.addWidget(select_none_btn)
        select_row.addWidget(self.list_status, stretch=1)
        layout.addLayout(select_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, SPACING_SM, 0)
        left_layout.setSpacing(SPACING_SM)
        self.test_tree = QTreeWidget()
        self.test_tree.setHeaderLabels(["Description"])
        self.test_tree.setColumnCount(1)
        self.test_tree.setUniformRowHeights(True)
        self.test_tree.setRootIsDecorated(True)
        self.test_tree.setMinimumWidth(420)
        self.test_tree.setMinimumHeight(280)
        self.test_tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.test_tree.setToolTip(
            "Double-click a test to run it alone. Right-click → Run this test. "
            "Hover for the technical pytest id."
        )
        self.test_tree.header().setStretchLastSection(True)
        self.test_tree.itemChanged.connect(self._on_tree_item_changed)
        self.test_tree.itemClicked.connect(self._on_tree_item_clicked)
        self.test_tree.itemDoubleClicked.connect(self._on_tree_double_clicked)
        self.test_tree.currentItemChanged.connect(self._on_current_item_changed)
        self.test_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.test_tree.customContextMenuRequested.connect(self._on_tree_context_menu)
        self._last_test_item: QTreeWidgetItem | None = None
        self._last_nodeid: str | None = None
        left_layout.addWidget(self.test_tree, stretch=1)

        action_row = QHBoxLayout()
        action_row.setSpacing(SPACING_SM)
        self.run_one_btn = make_primary_button("Run This")
        self.run_one_btn.setToolTip("Run the orange-highlighted test (✓ not required)")
        self.run_one_btn.clicked.connect(self._on_run_highlighted)
        self.run_btn = make_secondary_button("Run Checked")
        self.run_btn.setToolTip("Run all tests marked with ✓")
        self.run_btn.setStyleSheet(f"color: {COLOR_TEXT};")
        self.run_btn.clicked.connect(self._on_run)
        self.open_html_btn = make_secondary_button("Open HTML Report")
        self.open_html_btn.setEnabled(False)
        self.open_html_btn.clicked.connect(self._on_open_html)
        self.open_allure_btn = make_secondary_button("Open Allure")
        self.open_allure_btn.setEnabled(False)
        self.open_allure_btn.setToolTip("Open the latest Allure HTML report in the browser")
        self.open_allure_btn.clicked.connect(self._on_open_allure)
        self.allure_history_combo = QComboBox()
        self.allure_history_combo.setMinimumWidth(160)
        self.allure_history_combo.setToolTip("Last ≤20 archived Allure runs")
        self.allure_history_combo.setEnabled(False)
        self.open_allure_history_btn = make_secondary_button("Open History")
        self.open_allure_history_btn.setEnabled(False)
        self.open_allure_history_btn.setToolTip("Open the selected archived Allure run")
        self.open_allure_history_btn.clicked.connect(self._on_open_allure_history)
        action_row.addWidget(self.run_one_btn)
        action_row.addWidget(self.run_btn)
        action_row.addWidget(self.open_html_btn)
        action_row.addWidget(self.open_allure_btn)
        action_row.addWidget(self.allure_history_combo)
        action_row.addWidget(self.open_allure_history_btn)
        action_row.addStretch()
        left_layout.addLayout(action_row)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(SPACING_SM, 0, 0, 0)
        right_layout.setSpacing(SPACING_SM)

        self.summary_label = make_muted_label("עדיין לא הורצו טסטים.")
        self.summary_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.summary_label.setWordWrap(True)
        right_layout.addWidget(self.summary_label)

        self.output_tabs = QTabWidget()
        self.results_list = QListWidget()
        self.results_list.setToolTip("Results of the last run")
        self.log_view = make_log_view(min_height=160)
        self._log_bridge.line.connect(lambda line: append_log_limited(self.log_view, line))
        self.output_tabs.addTab(self.results_list, "Results")
        self.output_tabs.addTab(self.log_view, "Live Log")
        right_layout.addWidget(self.output_tabs, stretch=1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([720, 480])
        layout.addWidget(splitter, stretch=1)

        add_dialog_footer(layout, self)
        self._apply_default_geometry()
        self._refresh_allure_history()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._geometry_applied:
            self._apply_default_geometry()
            self._geometry_applied = True
        ok, message = ensure_repo_dir(self._repo_dir())
        if ok and not self._nodeids:
            self.list_status.setText(message + " — לחץ Refresh Test List.")

    def _apply_default_geometry(self) -> None:
        """Open large by default (~90% of available screen), centered."""
        screen = self.screen()
        if screen is None:
            app = QApplication.instance()
            screen = app.primaryScreen() if app is not None else None
        if screen is None:
            self.resize(1280, 900)
            return
        avail = screen.availableGeometry()
        width = max(self.minimumWidth(), min(1400, int(avail.width() * 0.92)))
        height = max(self.minimumHeight(), min(980, int(avail.height() * 0.90)))
        self.resize(width, height)
        frame = self.frameGeometry()
        frame.moveCenter(avail.center())
        self.move(frame.topLeft())

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._busy() or (self._front_worker is not None and self._front_worker.isRunning()):
            from nexus_toolkit.ui.widgets import confirm_action

            if not confirm_action(
                self,
                "טסטים רצים",
                "יש פעולה פעילה (איסוף / הרצה / Front). לסגור בכל זאת?",
            ):
                event.ignore()
                return
        super().closeEvent(event)

    def _repo_dir(self) -> Path:
        return Path(self.repo_edit.text().strip() or str(DEFAULT_NEXUS_TESTS_DIR)).expanduser()

    def _save_config(self) -> None:
        tests_cfg = self.services.config.setdefault("tests", {})
        tests_cfg["repo_dir"] = str(self._repo_dir())
        tests_cfg["git_url"] = self.git_url_edit.text().strip() or DEFAULT_NEXUS_TESTS_GIT
        save_config(self.services.config)

    def _busy(self) -> bool:
        return (
            (self._git_worker is not None and self._git_worker.isRunning())
            or (self._collect_worker is not None and self._collect_worker.isRunning())
            or (self._run_worker is not None and self._run_worker.isRunning())
        )

    def _set_busy(self, busy: bool) -> None:
        self.git_btn.setEnabled(not busy)
        self.refresh_btn.setEnabled(not busy)
        self.run_btn.setEnabled(not busy)
        self.run_one_btn.setEnabled(not busy)
        self.repo_edit.setEnabled(not busy)
        self.git_url_edit.setEnabled(not busy)

    def _on_browse_repo(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select nexus-tests directory", str(self._repo_dir()))
        if path:
            self.repo_edit.setText(path)
            self._save_config()

    def _on_git_update(self) -> None:
        if self._busy():
            return
        self._save_config()
        self.log_view.clear()
        self.output_tabs.setCurrentWidget(self.log_view)
        self._set_busy(True)
        self._git_worker = TestsGitWorker(
            self._repo_dir(),
            self.git_url_edit.text().strip() or DEFAULT_NEXUS_TESTS_GIT,
            parent=self,
        )
        self._git_worker.line.connect(self._log_bridge.line.emit)
        self._git_worker.finished.connect(self._on_git_finished)
        self._git_worker.start()

    def _on_git_finished(self, ok: bool, message: str) -> None:
        self._git_worker = None
        self._set_busy(False)
        self._log_bridge.line.emit(message)
        if ok:
            QMessageBox.information(self, "Git", message)
        else:
            QMessageBox.warning(self, "Git Failed", message)

    def _current_suite(self) -> tuple[str, str]:
        name = self.suite_combo.currentText()
        return SUITE_PRESETS.get(name, ("tests/", ""))

    def _on_refresh_list(self) -> None:
        if self._busy():
            return
        self._save_config()
        suite_path, markers = self._current_suite()
        lab = self.lab_cb.isChecked() or name_is_lab(self.suite_combo.currentText())
        if self.flight_cb.isChecked() and "flight" not in markers:
            markers = "flight" if not markers else f"({markers}) and flight"

        self.log_view.clear()
        self.output_tabs.setCurrentWidget(self.log_view)
        self.list_status.setText("Collecting tests…")
        self._set_busy(True)
        self._collect_worker = TestsCollectWorker(
            self._repo_dir(),
            suite_path,
            markers,
            drone=self.drone_cb.isChecked(),
            lab=lab,
            parent=self,
        )
        self._collect_worker.line.connect(self._log_bridge.line.emit)
        self._collect_worker.finished.connect(self._on_collect_finished)
        self._collect_worker.start()

    def _on_collect_finished(self, ok: bool, collected: list, message: str) -> None:
        self._collect_worker = None
        self._set_busy(False)
        items: list[CollectedTest] = []
        for row in collected:
            if isinstance(row, CollectedTest):
                items.append(row)
            elif isinstance(row, str):
                items.append(CollectedTest(nodeid=row))
            elif isinstance(row, dict):
                items.append(
                    CollectedTest(
                        nodeid=str(row.get("nodeid") or ""),
                        description=str(row.get("description") or ""),
                    )
                )
        self._nodeids = [item.nodeid for item in items if item.nodeid]
        self._descriptions = {
            item.nodeid: item.description for item in items if item.nodeid
        }
        self._populate_test_tree(items)
        missing = sum(1 for item in items if item.nodeid and not (item.description or "").strip())
        if not ok:
            self.list_status.setText(f"Collect failed: {message}")
            QMessageBox.warning(self, "Collect Failed", message)
        elif missing:
            self.list_status.setText(f"{message} — {missing} without docstring (fallback name).")
        else:
            self.list_status.setText(message)

    def _populate_test_tree(self, collected: list[CollectedTest]) -> None:
        self._updating_checks = True
        self.test_tree.blockSignals(True)
        self.test_tree.clear()
        groups: dict[str, QTreeWidgetItem] = {}
        for item in collected:
            if not item.nodeid:
                continue
            info = parse_test_display(item.nodeid, item.description)
            group_item = groups.get(info.group)
            if group_item is None:
                # Group headers are labels only — no checkbox (avoids AutoTristate fighting one child).
                group_item = QTreeWidgetItem([info.group])
                group_item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                )
                group_item.setForeground(0, QBrush(QColor(COLOR_TEXT_SOFT)))
                group_item.setToolTip(0, f"{info.kind} group")
                self.test_tree.addTopLevelItem(group_item)
                groups[info.group] = group_item

            child = QTreeWidgetItem([info.title])
            child.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            child.setCheckState(0, Qt.CheckState.Checked)
            child.setData(0, Qt.ItemDataRole.UserRole, item.nodeid)
            tip = item.nodeid
            if info.description:
                tip = f"{info.description}\n\n{item.nodeid}"
            else:
                tip = f"(no docstring)\n\n{item.nodeid}"
            child.setToolTip(0, tip)
            group_item.addChild(child)

        self.test_tree.expandAll()
        self._last_test_item = None
        self._last_nodeid = None
        self.test_tree.blockSignals(False)
        self._updating_checks = False

    def _remember_test_item(self, item: QTreeWidgetItem | None) -> None:
        nodeid = self._nodeid_from_item(item)
        if not nodeid or item is None:
            return
        self._last_test_item = item
        self._last_nodeid = nodeid
        self.test_tree.setCurrentItem(item)

    def _on_current_item_changed(
        self,
        current: QTreeWidgetItem | None,
        _previous: QTreeWidgetItem | None,
    ) -> None:
        self._remember_test_item(current)

    def _on_tree_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        """Remember the orange-highlighted test even when its ✓ is empty."""
        self._remember_test_item(item)

    def _on_tree_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._updating_checks or column != 0:
            return
        # Only leaf tests are checkable — no parent sync.
        if self._nodeid_from_item(item):
            self._remember_test_item(item)

    def _select_all(self) -> None:
        self._set_all_checks(Qt.CheckState.Checked)

    def _select_none(self) -> None:
        self._set_all_checks(Qt.CheckState.Unchecked)

    def _set_all_checks(self, state: Qt.CheckState) -> None:
        self._updating_checks = True
        self.test_tree.blockSignals(True)
        root = self.test_tree.invisibleRootItem()
        for i in range(root.childCount()):
            group = root.child(i)
            for j in range(group.childCount()):
                group.child(j).setCheckState(0, state)
        self.test_tree.blockSignals(False)
        self._updating_checks = False

    def _selected_nodeids(self) -> list[str]:
        selected: list[str] = []
        root = self.test_tree.invisibleRootItem()
        for i in range(root.childCount()):
            group = root.child(i)
            for j in range(group.childCount()):
                child = group.child(j)
                if child.checkState(0) == Qt.CheckState.Checked:
                    nodeid = child.data(0, Qt.ItemDataRole.UserRole)
                    if nodeid:
                        selected.append(str(nodeid))
        return selected

    def _build_options(self, selected: list[str]) -> TestRunOptions:
        suite_path, markers = self._current_suite()
        if self.flight_cb.isChecked() and "flight" not in markers:
            markers = "flight" if not markers else f"({markers}) and flight"
        return TestRunOptions(
            headless=self.headless_cb.isChecked(),
            parallel=self.parallel_cb.isChecked(),
            parallel_workers=self.parallel_workers.value(),
            allure=self.allure_cb.isChecked(),
            drone=self.drone_cb.isChecked(),
            lab=self.lab_cb.isChecked() or name_is_lab(self.suite_combo.currentText()),
            flight=self.flight_cb.isChecked(),
            reruns=self.reruns_spin.value(),
            browser=self.browser_combo.currentText(),
            marker_expression=markers,
            suite_path=suite_path,
        )

    def _nodeid_from_item(self, item: QTreeWidgetItem | None) -> str | None:
        if item is None:
            return None
        nodeid = item.data(0, Qt.ItemDataRole.UserRole)
        return str(nodeid) if nodeid else None

    def _resolve_single_test_nodeid(self) -> str | None:
        """Orange-highlighted / last-clicked test — independent of ✓ state."""
        if self._last_nodeid:
            return self._last_nodeid
        for candidate in (self.test_tree.currentItem(), self._last_test_item):
            nodeid = self._nodeid_from_item(candidate)
            if nodeid:
                return nodeid
        current = self.test_tree.currentItem()
        if current is not None and current.childCount() > 0:
            return self._nodeid_from_item(current.child(0))
        checked = self._selected_nodeids()
        if len(checked) == 1:
            return checked[0]
        return None

    def _on_tree_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        self._remember_test_item(item)
        nodeid = self._nodeid_from_item(item)
        if nodeid:
            self._start_run([nodeid])

    def _on_tree_context_menu(self, pos) -> None:
        item = self.test_tree.itemAt(pos)
        nodeid = self._nodeid_from_item(item)
        if not nodeid or item is None:
            return
        self._remember_test_item(item)
        menu = QMenu(self)
        run_action = QAction("Run this test", self)
        run_action.triggered.connect(lambda: self._start_run([nodeid]))
        menu.addAction(run_action)
        check_only = QAction("Check only this test", self)
        check_only.triggered.connect(lambda: self._check_only(item))
        menu.addAction(check_only)
        menu.exec(self.test_tree.viewport().mapToGlobal(pos))

    def _check_only(self, item: QTreeWidgetItem) -> None:
        self._set_all_checks(Qt.CheckState.Unchecked)
        self._updating_checks = True
        item.setCheckState(0, Qt.CheckState.Checked)
        self._updating_checks = False
        self._remember_test_item(item)

    def _on_run_highlighted(self) -> None:
        nodeid = self._resolve_single_test_nodeid()
        if not nodeid:
            QMessageBox.information(
                self,
                "No Test",
                "לחץ על טסט ברשימה (השורה הכתומה) ואז Run This.\n"
                "אין צורך לסמן ✓.",
            )
            return
        self._start_run([nodeid])

    def _on_run(self) -> None:
        selected = self._selected_nodeids()
        if not selected:
            nodeid = self._resolve_single_test_nodeid()
            if nodeid:
                self._start_run([nodeid])
                return
            QMessageBox.information(
                self,
                "No Tests",
                "סמן טסטים ב־✓ להרצה מרובה, או לחץ על טסט ואז Run This.",
            )
            return
        self._start_run(selected)

    def _start_run(self, selected: list[str]) -> None:
        if self._busy():
            QMessageBox.information(self, "Busy", "פעולה אחרת עדיין רצה — המתן שתסתיים.")
            return
        if not selected:
            return

        self._save_config()
        options = self._build_options(selected)

        needs_front = any("/e2e/" in n or n.startswith("tests/e2e") for n in selected)
        if needs_front:
            ok, message = check_vite_running(DEFAULT_VITE_URL)
            if not ok:
                if not self._warn_front_missing(message):
                    return

        self.log_view.clear()
        self.summary_label.setText(f"Running {len(selected)} test(s)…")
        self.results_list.clear()
        self.open_html_btn.setEnabled(False)
        self.output_tabs.setCurrentWidget(self.log_view)
        self._set_busy(True)
        self._run_worker = TestsRunWorker(self._repo_dir(), selected, options, parent=self)
        self._run_worker.line.connect(self._log_bridge.line.emit)
        self._run_worker.finished.connect(self._on_run_finished)
        self._run_worker.start()

    def _warn_front_missing(self, message: str) -> bool:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Front לא רץ")
        box.setText(
            "ה-Front (Vite) לא זמין — טסטי UI עלולים להיכשל.\n\n"
            f"{message}\n\n"
            "אפשר להרים Front עכשיו או להמשיך בכל זאת."
        )
        start_btn = box.addButton("Start Front — הרם Front", QMessageBox.ButtonRole.ActionRole)
        continue_btn = box.addButton("המשך בכל זאת", QMessageBox.ButtonRole.AcceptRole)
        cancel_btn = box.addButton("ביטול", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked == cancel_btn:
            return False
        if clicked == start_btn:
            self._start_front()
            return True
        return clicked == continue_btn

    def _start_front(self) -> None:
        if self._front_worker is not None and self._front_worker.isRunning():
            return
        app_dir = resolve_frontend_app_dir(self.services.config)
        self.output_tabs.setCurrentWidget(self.log_view)
        self._log_bridge.line.emit(f"Starting Front: {app_dir}")
        self._front_worker = FrontDevWorker(self.services.frontend_runner, app_dir, parent=self)
        self._front_worker.line.connect(self._log_bridge.line.emit)
        self._front_worker.finished.connect(self._on_front_finished)
        self._front_worker.start()

    def _on_front_finished(self, success: bool, message: str) -> None:
        self._log_bridge.line.emit(message)
        if not success and "stopped" not in message.lower():
            QMessageBox.warning(self, "Start Front", message)

    def _on_run_finished(self, ok: bool, summary: object) -> None:
        self._run_worker = None
        self._set_busy(False)
        if not isinstance(summary, TestRunSummary):
            return
        self._last_summary = summary
        self._fill_results_list(summary)
        self.output_tabs.setCurrentWidget(self.results_list)

        html_ready = bool(summary.html_report and summary.html_report.is_file())
        self.open_html_btn.setEnabled(html_ready)
        allure_ready = bool(
            summary.allure_report_dir and (summary.allure_report_dir / "index.html").is_file()
        )
        self.open_allure_btn.setEnabled(allure_ready or bool(list_allure_archives()))
        self._refresh_allure_history()

        text = (
            f"Selected: {summary.selected_count}  ·  Ran: {summary.total_executed}\n"
            f"Passed: {summary.passed}  ·  Failed: {summary.failed}  ·  "
            f"Skipped: {summary.skipped}  ·  Errors: {summary.errors}  ·  Exit: {summary.exit_code}"
        )
        if html_ready:
            text += f"\nHTML: {summary.html_report}"
        if allure_ready:
            text += f"\nAllure: {summary.allure_report_dir}"
        if summary.allure_archive_dir:
            text += f"\nAllure archive: {summary.allure_archive_dir.name}"
        if summary.allure_error:
            text += f"\nAllure: {summary.allure_error}"
        self.summary_label.setText(text)

        title = "Tests Passed" if ok else "Tests Finished with Failures"
        detail = (
            f"Selected: {summary.selected_count}\n"
            f"Passed: {summary.passed}\n"
            f"Failed: {summary.failed}\n"
            f"Skipped: {summary.skipped}\n"
            f"Errors: {summary.errors}"
        )
        if html_ready:
            detail += "\n\nOpen HTML Report via the button in the dialog."
        if allure_ready:
            detail += "\nOpen Allure via the button in the dialog."
        elif summary.allure_error:
            detail += f"\n\nAllure: {summary.allure_error}"
        if ok:
            QMessageBox.information(self, title, detail)
        else:
            QMessageBox.warning(self, title, detail)

    def _fill_results_list(self, summary: TestRunSummary) -> None:
        self.results_list.clear()
        prefix = {
            "passed": "PASS",
            "failed": "FAIL",
            "skipped": "SKIP",
            "error": "ERROR",
        }
        colors = {
            "passed": COLOR_SUCCESS,
            "failed": COLOR_ERROR,
            "error": COLOR_ERROR,
            "skipped": COLOR_WARNING,
        }
        order = {"failed": 0, "error": 1, "skipped": 2, "passed": 3}
        cases = sorted(summary.cases, key=lambda c: (order.get(c.outcome, 9), c.nodeid))
        for case in cases:
            description = self._lookup_description(case.nodeid)
            info = parse_test_display(case.nodeid, description)
            label = f"[{prefix.get(case.outcome, case.outcome.upper())}]  {info.title}"
            item = QListWidgetItem(label)
            tip = case.nodeid
            if info.description:
                tip = f"{info.description}\n\n{case.nodeid}"
            if case.message:
                tip += "\n\n" + case.message[:2000]
            item.setToolTip(tip)
            color = colors.get(case.outcome, COLOR_MUTED)
            item.setForeground(QBrush(QColor(color)))
            self.results_list.addItem(item)
        if not cases and summary.selected_count:
            self.results_list.addItem(
                QListWidgetItem("(no per-test results — see Live Log / Open HTML Report)")
            )

    def _lookup_description(self, nodeid: str) -> str:
        if nodeid in self._descriptions:
            return self._descriptions[nodeid]
        # JUnit nodeids sometimes drop ".py"
        for key, value in self._descriptions.items():
            if key.replace(".py", "") == nodeid.replace(".py", ""):
                return value
            if key.endswith(nodeid) or nodeid.endswith(key.split("::")[-1]):
                base = key.split("::")[-1].split("[")[0]
                other = nodeid.split("::")[-1].split("[")[0]
                if base == other:
                    return value
        return ""

    def _on_open_html(self) -> None:
        if not self._last_summary or not self._last_summary.html_report:
            return
        path = self._last_summary.html_report
        if not path.is_file():
            QMessageBox.warning(self, "HTML Report", f"Report not found:\n{path}")
            return
        import webbrowser

        webbrowser.open(path.as_uri())

    def _refresh_allure_history(self) -> None:
        self.allure_history_combo.blockSignals(True)
        self.allure_history_combo.clear()
        archives = list_allure_archives()
        for path in archives:
            self.allure_history_combo.addItem(path.name, str(path))
        has_archives = bool(archives)
        self.allure_history_combo.setEnabled(has_archives)
        self.open_allure_history_btn.setEnabled(has_archives)
        latest = allure_dirs().report
        if (latest / "index.html").is_file() or has_archives:
            self.open_allure_btn.setEnabled(True)
        self.allure_history_combo.blockSignals(False)

    def _on_open_allure(self) -> None:
        report_dir: Path | None = None
        if self._last_summary and self._last_summary.allure_report_dir:
            candidate = self._last_summary.allure_report_dir
            if (candidate / "index.html").is_file():
                report_dir = candidate
        if report_dir is None:
            latest = allure_dirs().report
            if (latest / "index.html").is_file():
                report_dir = latest
        if report_dir is None:
            archives = list_allure_archives()
            if archives:
                report_dir = archives[0]
        if report_dir is None:
            QMessageBox.warning(
                self,
                "Allure",
                "No Allure report found yet.\nRun tests with Allure checked first.",
            )
            return
        ok, message = open_allure_report(report_dir)
        self._log_bridge.line.emit(message)
        if not ok:
            QMessageBox.warning(self, "Allure", message)

    def _on_open_allure_history(self) -> None:
        path_str = self.allure_history_combo.currentData()
        if not path_str:
            QMessageBox.warning(self, "Allure History", "No archived Allure run selected.")
            return
        report_dir = Path(str(path_str))
        if not (report_dir / "index.html").is_file():
            QMessageBox.warning(self, "Allure History", f"Report not found:\n{report_dir}")
            self._refresh_allure_history()
            return
        ok, message = open_allure_report(report_dir)
        self._log_bridge.line.emit(message)
        if not ok:
            QMessageBox.warning(self, "Allure History", message)


def _section_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("class", "section-title")
    label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    return label


def name_is_lab(suite_name: str) -> bool:
    return suite_name.strip().lower() == "lab"
