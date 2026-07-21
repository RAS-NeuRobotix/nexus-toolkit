"""Full-screen dialog for Jira bug search."""

from __future__ import annotations

import webbrowser

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from nexus_toolkit.config import (
    get_cloud_repo_url,
    get_cursor_api_key,
    get_cursor_model,
    get_jira_fast_search,
    save_config,
)
from nexus_toolkit.paths import JIRA_BROWSE_BASE
from nexus_toolkit.services.cursor_agent import build_search_prompt
from nexus_toolkit.services.mcp_config import atlassian_mcp_status
from nexus_toolkit.ui.agent_worker import AgentWorker
from nexus_toolkit.ui.design_system import (
    COLOR_BLUE,
    COLOR_PRIMARY,
    COLOR_SURFACE,
    COLOR_SURFACE_ALT,
    status_color,
)
from nexus_toolkit.ui.jira_result_formatter import extract_issue_keys, format_jira_report_html


class BugSearchDialog(QDialog):
    def __init__(self, config: dict, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self._worker: AgentWorker | None = None
        self._streaming = False

        self.setWindowTitle("חיפוש באג קיים / Search Existing Bug")
        self.resize(900, 700)

        layout = QVBoxLayout(self)

        hint = QLabel(
            "תאר את הבאג לחיפוש כפילויות וריגרסיות. "
            "כתיבה בעברית תחזיר תוצאה בעברית."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.search_input = QTextEdit()
        self.search_input.setPlaceholderText(
            "לדוגמה: מפת DTM לא נטענת ב-nexus-core אחרי עדכון..."
        )
        self.search_input.setMaximumHeight(140)
        layout.addWidget(self.search_input)

        self.fast_search_cb = QCheckBox(
            "חיפוש מהיר (שאילתה אחת, ~20–40 שנ') — מומלץ"
        )
        self.fast_search_cb.setChecked(get_jira_fast_search(config))
        self.fast_search_cb.setToolTip(
            "חיפוש מהיר: JQL אחת, בלי העשרת באגים — מהיר יותר.\n"
            "חיפוש מלא: 3 שאילתות + פרטי באג — מדויק יותר לריגרסיות."
        )
        layout.addWidget(self.fast_search_cb)

        btn_row = QHBoxLayout()
        self.search_btn = QPushButton("חיפוש באג / Search Bug")
        self.search_btn.clicked.connect(self._on_search)
        self.close_btn = QPushButton("סגור / Close")
        self.close_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.search_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.close_btn)
        layout.addLayout(btn_row)

        self.mcp_status_label = QLabel("")
        self.mcp_status_label.setWordWrap(True)
        ok, hint = atlassian_mcp_status()
        self.mcp_status_label.setStyleSheet(
            f"color: {status_color(ok)}; font-size: 11px;"
        )
        self.mcp_status_label.setText(hint)
        layout.addWidget(self.mcp_status_label)

        output_label = QLabel("תוצאות / Results:")
        layout.addWidget(output_label)

        self.issue_links_container = QWidget()
        self.issue_links_row = QHBoxLayout(self.issue_links_container)
        self.issue_links_row.setContentsMargins(0, 0, 0, 0)
        self.issue_links_container.setVisible(False)
        layout.addWidget(self.issue_links_container)

        self.search_output = QTextBrowser()
        self.search_output.setOpenExternalLinks(True)
        self.search_output.setPlaceholderText("תוצאות החיפוש יופיעו כאן...")
        font = QFont()
        font.setPointSize(11)
        self.search_output.setFont(font)
        layout.addWidget(self.search_output, stretch=1)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        self.open_jira_btn = QPushButton("פתח ב-Jira / Open in Jira")
        self.open_jira_btn.setVisible(False)
        self.open_jira_btn.clicked.connect(self._open_in_jira)
        layout.addWidget(self.open_jira_btn)

        self._last_key: str | None = None
        self._issue_link_buttons: list[QPushButton] = []

    def _open_in_jira(self) -> None:
        if self._last_key:
            webbrowser.open(f"{JIRA_BROWSE_BASE}/{self._last_key}")

    def _open_issue(self, key: str) -> None:
        webbrowser.open(f"{JIRA_BROWSE_BASE}/{key}")

    def _clear_issue_links(self) -> None:
        while self.issue_links_row.count():
            item = self.issue_links_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._issue_link_buttons.clear()
        self.issue_links_container.setVisible(False)

    def _show_issue_links(self, keys: list[str]) -> None:
        self._clear_issue_links()
        if not keys:
            return

        label = QLabel("באגים שנמצאו — לחץ לפתיחה:")
        label.setStyleSheet("font-weight: bold;")
        self.issue_links_row.addWidget(label)

        for key in keys[:8]:
            btn = QPushButton(key)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                f"QPushButton {{ color: {COLOR_BLUE}; font-weight: bold; "
                f"border: 1px solid {COLOR_PRIMARY}; border-radius: 4px; "
                f"padding: 4px 10px; background: {COLOR_SURFACE_ALT}; }}"
                f"QPushButton:hover {{ background: {COLOR_SURFACE}; "
                f"border-color: {COLOR_BLUE}; }}"
            )
            btn.clicked.connect(lambda _checked=False, k=key: self._open_issue(k))
            self.issue_links_row.addWidget(btn)
            self._issue_link_buttons.append(btn)

        self.issue_links_row.addStretch()
        self.issue_links_container.setVisible(True)

    def _require_api_key(self) -> str | None:
        api_key = get_cursor_api_key(self.config)
        if not api_key:
            QMessageBox.warning(
                self,
                "API Key Required",
                "הגדר Cursor API Key ב-File → Settings",
            )
            return None
        return api_key

    def _on_search(self) -> None:
        description = self.search_input.toPlainText().strip()
        if not description:
            QMessageBox.information(self, "קלט נדרש", "הזן תיאור באג לחיפוש.")
            return
        api_key = self._require_api_key()
        if not api_key:
            return

        if self._worker and self._worker.isRunning():
            QMessageBox.information(self, "עסוק", "חיפוש כבר רץ.")
            return

        self.search_output.clear()
        self._clear_issue_links()
        self.open_jira_btn.setVisible(False)
        self.search_btn.setEnabled(False)
        fast = self.fast_search_cb.isChecked()
        if fast:
            self.status_label.setText("מחפש (מצב מהיר)...")
            self.search_output.setPlainText("מחפש באגים דומים ב-Jira...\n")
        else:
            self.status_label.setText("מחפש (מצב מלא)...")
        self._streaming = not fast

        self.config.setdefault("jira", {})["fast_search"] = fast
        save_config(self.config)

        model = get_cursor_model(self.config)
        cloud_repo = get_cloud_repo_url(self.config)
        self._worker = AgentWorker(
            build_search_prompt(description, fast=fast),
            api_key,
            model,
            cloud_repo,
            fast=fast,
            parent=self,
        )
        self._worker.chunk.connect(self._on_chunk)
        self._worker.finished_ok.connect(self._on_finished_ok)
        self._worker.finished_err.connect(self._on_finished_err)
        self._worker.start()

    def _on_chunk(self, text: str) -> None:
        if not self._streaming:
            return
        cursor = self.search_output.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(text)
        self.search_output.setTextCursor(cursor)
        self.search_output.ensureCursorVisible()

    def _apply_formatted_result(self, result: str) -> None:
        self._streaming = False
        self.search_output.setHtml(format_jira_report_html(result))
        keys = extract_issue_keys(result)
        self._show_issue_links(keys)
        self._last_key = keys[0] if keys else None
        if self._last_key:
            self.status_label.setText(f"נמצאו {len(keys)} באגים — הראשון: {self._last_key}")
            self.open_jira_btn.setVisible(True)
        else:
            self.status_label.setText("החיפוש הושלם")
            self.open_jira_btn.setVisible(False)

    def _on_finished_ok(self, result: str) -> None:
        self.search_btn.setEnabled(True)
        self._apply_formatted_result(result)

    def _on_finished_err(self, error: str) -> None:
        self.search_btn.setEnabled(True)
        self._streaming = False
        self.status_label.setText(f"שגיאה: {error}")
        self.open_jira_btn.setVisible(False)
        self._clear_issue_links()
        QMessageBox.critical(self, "שגיאת סוכן", error)
