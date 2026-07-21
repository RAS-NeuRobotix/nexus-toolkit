"""Full-screen dialog for creating a new Jira bug."""

from __future__ import annotations

import webbrowser
from pathlib import Path

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from nexus_toolkit.app_state import app_state
from nexus_toolkit.config import get_cloud_repo_url, get_cursor_api_key, get_cursor_model
from nexus_toolkit.models import BugDraft
from nexus_toolkit.paths import JIRA_BROWSE_BASE
from nexus_toolkit.services.draft_enrichment import (
    build_local_draft_from_description,
    enrich_draft_from_description,
)
from nexus_toolkit.services.cursor_agent import build_generate_prompt, build_open_bug_prompt
from nexus_toolkit.ui.agent_worker import AgentWorker
from nexus_toolkit.utils import (
    build_missing_fields_message_he,
    extract_issue_key,
    parse_bug_draft,
    zip_recording,
)


class BugCreateDialog(QDialog):
    def __init__(self, config: dict, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.draft = BugDraft()
        self._worker: AgentWorker | None = None
        self._pending_action: str | None = None

        self.setWindowTitle("יצירת באג חדש / Create New Bug")
        self.resize(1000, 750)

        root = QHBoxLayout(self)

        left = QVBoxLayout()
        left.addWidget(QLabel("תיאור הבאג (חופשי):"))
        self.bug_description = QTextEdit()
        self.bug_description.setPlaceholderText(
            "תאר את הבאג במשפט או שניים — המערכת תשלים צעדים, מצופה ובפועל.\n"
            "לדוגמה: רחפן חוצה אזור אסור בזמן טיסה"
        )
        left.addWidget(self.bug_description)

        self.analyze_logs_cb = QCheckBox("נתח לוגים גם כן / Analyze logs too")
        self.analyze_logs_cb.setChecked(False)
        left.addWidget(self.analyze_logs_cb)

        self.recording_path_label = QLabel()
        self.recording_path_label.setWordWrap(True)
        self.recording_path_label.setProperty("class", "muted")
        left.addWidget(self.recording_path_label)

        self.generate_btn = QPushButton("Generate Bug Draft")
        self.generate_btn.clicked.connect(self._on_generate)
        left.addWidget(self.generate_btn)

        left.addWidget(QLabel("תצוגת טיוטה (אנגלית):"))
        self.draft_preview = QTextEdit()
        self.draft_preview.setReadOnly(True)
        left.addWidget(self.draft_preview, stretch=1)

        attach_row = QHBoxLayout()
        self.attach_logs_cb = QCheckBox("צרף לוגים לבאג / Attach latest logs")
        self.attach_logs_cb.setChecked(False)
        attach_row.addWidget(self.attach_logs_cb)
        attach_row.addStretch()
        self.open_bug_btn = QPushButton("Open Bug")
        self.open_bug_btn.clicked.connect(self._on_open_bug)
        attach_row.addWidget(self.open_bug_btn)
        left.addLayout(attach_row)

        close_btn = QPushButton("סגור / Close")
        close_btn.clicked.connect(self.reject)
        left.addWidget(close_btn)

        root.addLayout(left, stretch=3)

        right = QVBoxLayout()
        right.addWidget(QLabel("✎ עריכת באג / Edit Bug"))

        self.edit_panel = QWidget()
        edit_layout = QVBoxLayout(self.edit_panel)
        self.summary_edit = QTextEdit()
        self.summary_edit.setMaximumHeight(60)
        self.steps_edit = QTextEdit()
        self.expected_edit = QTextEdit()
        self.expected_edit.setMaximumHeight(80)
        self.actual_edit = QTextEdit()
        self.actual_edit.setMaximumHeight(80)

        for label, widget in (
            ("Summary", self.summary_edit),
            ("Steps to Reproduce", self.steps_edit),
            ("Expected Result", self.expected_edit),
            ("Actual Result", self.actual_edit),
        ):
            edit_layout.addWidget(QLabel(label))
            edit_layout.addWidget(widget)
            widget.textChanged.connect(self._sync_draft_from_edits)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.edit_panel)
        right.addWidget(scroll, stretch=1)

        self.status_label = QLabel("")
        right.addWidget(self.status_label)

        root.addLayout(right, stretch=2)

        self._update_log_controls()

    def prefill(
        self,
        *,
        description: str = "",
        draft: BugDraft | None = None,
        log_dir: Path | None = None,
        analyze_logs: bool = False,
        attach_logs: bool = True,
    ) -> None:
        """Prefill create dialog from a log investigation session."""
        if log_dir is not None:
            app_state.set_recording_path(log_dir)
        self._update_log_controls()
        if description:
            self.bug_description.setPlainText(description)
        if draft is not None:
            self.draft = draft
            self._apply_draft_to_edits()
        if app_state.has_recording():
            self.analyze_logs_cb.setChecked(analyze_logs)
            self.attach_logs_cb.setChecked(attach_logs)
            self.analyze_logs_cb.setEnabled(True)
            self.attach_logs_cb.setEnabled(True)

    def _update_log_controls(self) -> None:
        has_recording = app_state.has_recording()
        path = app_state.last_recording_path
        if has_recording and path:
            log_files = sorted(p.name for p in path.glob("*.log"))
            files_line = ", ".join(log_files) if log_files else "(no .log files yet)"
            self.recording_path_label.setText(f"Logs folder: {path}\nFiles: {files_line}")
            self.analyze_logs_cb.setEnabled(True)
            self.attach_logs_cb.setEnabled(True)
        else:
            self.recording_path_label.setText(
                "אין הקלטת לוגים — הקלט ב-Nexus Control תחילה.\n"
                "הלוגים נשמרים ב: ~/nexus-toolkit-logs/<timestamp>/"
            )
            self.analyze_logs_cb.setEnabled(False)
            self.analyze_logs_cb.setChecked(False)
            self.attach_logs_cb.setEnabled(False)
            self.attach_logs_cb.setChecked(False)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._update_log_controls()

    def _sync_draft_from_edits(self) -> None:
        self.draft.summary = self.summary_edit.toPlainText().strip()
        self.draft.steps_to_reproduce = self.steps_edit.toPlainText().strip()
        self.draft.expected_result = self.expected_edit.toPlainText().strip()
        self.draft.actual_result = self.actual_edit.toPlainText().strip()
        self.draft_preview.setPlainText(self.draft.to_markdown())

    def _apply_draft_to_edits(self) -> None:
        edits = (
            self.summary_edit,
            self.steps_edit,
            self.expected_edit,
            self.actual_edit,
        )
        for widget in edits:
            widget.blockSignals(True)
        try:
            self.summary_edit.setPlainText(self.draft.summary)
            self.steps_edit.setPlainText(self.draft.steps_to_reproduce)
            self.expected_edit.setPlainText(self.draft.expected_result)
            self.actual_edit.setPlainText(self.draft.actual_result)
            self.draft_preview.setPlainText(self.draft.to_markdown())
        finally:
            for widget in edits:
                widget.blockSignals(False)

    def _prefill_from_user_description(self, description: str) -> None:
        """Fill the full form from free text immediately (before agent returns)."""
        self.draft = build_local_draft_from_description(description)
        self._apply_draft_to_edits()

    def _require_api_key(self) -> str | None:
        api_key = get_cursor_api_key(self.config)
        if not api_key:
            QMessageBox.warning(self, "API Key Required", "הגדר Cursor API Key ב-File → Settings")
            return None
        return api_key

    def _set_busy(self, busy: bool) -> None:
        self.generate_btn.setEnabled(not busy)
        self.open_bug_btn.setEnabled(not busy)
        self.status_label.setText("עובד..." if busy else "")

    def _on_generate(self) -> None:
        description = self.bug_description.toPlainText().strip()
        if not description:
            QMessageBox.information(self, "קלט נדרש", "הזן תיאור באג.")
            return
        api_key = self._require_api_key()
        if not api_key:
            return

        log_dir = None
        if self.analyze_logs_cb.isChecked() and app_state.last_recording_path:
            log_dir = app_state.last_recording_path

        self._prefill_from_user_description(description)
        self.draft_preview.clear()
        self._pending_action = "generate"
        self._start_worker(build_generate_prompt(description, log_dir), api_key, fast=True)

    def _warn_incomplete_draft(self) -> bool:
        """Show Hebrew warning if draft is incomplete. Returns True if OK to proceed."""
        self._sync_draft_from_edits()
        if self.draft.is_complete() and not self.draft.needs_more_info:
            return True

        message = build_missing_fields_message_he(self.draft)
        QMessageBox.warning(
            self,
            "חסר מידע לבאג",
            message,
        )
        self.status_label.setText("יש למלא את כל השדות לפני פתיחת באג")
        return False

    def _on_open_bug(self) -> None:
        if not self._warn_incomplete_draft():
            return

        self._sync_draft_from_edits()
        if not self.draft.summary:
            QMessageBox.information(self, "טיוטה נדרשת", "צור טיוטת באג קודם (Generate).")
            return

        if self.draft.duplicate_warning:
            answer = QMessageBox.question(
                self,
                "כפילות אפשרית",
                f"ייתכן שזה כפילות של {self.draft.duplicate_warning}. ליצור בכל זאת?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        api_key = self._require_api_key()
        if not api_key:
            return

        attach_zip = None
        if self.attach_logs_cb.isChecked() and app_state.last_recording_path:
            attach_zip = zip_recording(app_state.last_recording_path)

        prompt = build_open_bug_prompt(
            self.draft.summary,
            self.draft.steps_to_reproduce,
            self.draft.expected_result,
            self.draft.actual_result,
            attach_zip,
        )
        self._pending_action = "open"
        self._start_worker(prompt, api_key)

    def _start_worker(self, prompt: str, api_key: str, *, fast: bool = False) -> None:
        if self._worker and self._worker.isRunning():
            QMessageBox.information(self, "עסוק", "משימה כבר רצה.")
            return
        self._set_busy(True)
        model = get_cursor_model(self.config)
        cloud_repo = get_cloud_repo_url(self.config)
        self._worker = AgentWorker(
            prompt, api_key, model, cloud_repo, fast=fast, parent=self
        )
        self._worker.chunk.connect(self._on_chunk)
        self._worker.finished_ok.connect(self._on_finished_ok)
        self._worker.finished_err.connect(self._on_finished_err)
        self._worker.start()

    def _on_chunk(self, text: str) -> None:
        cursor = self.draft_preview.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(text)

    def _on_finished_ok(self, result: str) -> None:
        self._set_busy(False)
        action = self._pending_action
        self._pending_action = None

        if action == "generate":
            description = self.bug_description.toPlainText().strip()
            data = parse_bug_draft(result)
            if data:
                agent_draft = BugDraft.from_dict(data)
                for field in (
                    "summary",
                    "steps_to_reproduce",
                    "expected_result",
                    "actual_result",
                ):
                    value = getattr(agent_draft, field, "").strip()
                    if value:
                        setattr(self.draft, field, value)
                if agent_draft.duplicate_warning:
                    self.draft.duplicate_warning = agent_draft.duplicate_warning
                self.draft = enrich_draft_from_description(description, self.draft)
                self._apply_draft_to_edits()
                if self.draft.is_complete() and not self.draft.needs_more_info:
                    self.status_label.setText("טיוטה נוצרה — בדוק ולחץ Open Bug")
                else:
                    self._warn_incomplete_draft()
            else:
                self.draft = enrich_draft_from_description(description, self.draft)
                self._apply_draft_to_edits()
                self.draft_preview.setPlainText(result)
                if self.draft.is_complete():
                    self.status_label.setText("טיוטה נוצרה מהתיאור שלך — בדוק ולחץ Open Bug")
                else:
                    self.status_label.setText("לא ניתן לפרסר את תשובת הסוכן — השלם ידנית")
                    QMessageBox.warning(
                        self,
                        "שגיאת טיוטה",
                        "לא הצלחתי לפרסר את תשובת הסוכן.\n"
                        "השדות מולאו מהתיאור שלך — בדוק ולחץ Open Bug.",
                    )
        elif action == "open":
            key = extract_issue_key(result)
            if key:
                url = f"{JIRA_BROWSE_BASE}/{key}"
                webbrowser.open(url)
                QMessageBox.information(self, "באג נוצר", f"נוצר {key}\n{url}")
            else:
                self.draft_preview.setPlainText(result)

    def _on_finished_err(self, error: str) -> None:
        self._set_busy(False)
        self._pending_action = None
        QMessageBox.critical(self, "שגיאת סוכן", error)
