"""Dialog for recording local and drone Nexus logs into one folder."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from nexus_toolkit.app_state import app_state
from nexus_toolkit.config import get_cloud_repo_url, get_cursor_api_key, get_cursor_model, save_config
from nexus_toolkit.models import BugDraft
from nexus_toolkit.paths import DEFAULT_CONTAINERS, LOGS_DIR
from nexus_toolkit.services.cursor_agent import build_log_investigation_prompt
from nexus_toolkit.services.draft_enrichment import (
    build_local_draft_from_description,
    enrich_draft_from_description,
)
from nexus_toolkit.services.drone_logs import DroneLogRecorder
from nexus_toolkit.services.nexus_services import NexusServices
from nexus_toolkit.ui.agent_worker import AgentWorker
from nexus_toolkit.ui.log_view import LogBridge
from nexus_toolkit.ui.widgets import (
    PasswordLineEdit,
    add_dialog_footer,
    configure_task_dialog,
    make_log_view,
    make_muted_label,
    make_primary_button,
    make_secondary_button,
    make_section_title,
)
from nexus_toolkit.utils import new_recording_dir, parse_bug_draft, reveal_in_file_manager


class LocalLogsDialog(QDialog):
    def __init__(self, services: NexusServices, parent=None) -> None:
        super().__init__(parent)
        self.services = services
        self._status_bridge = LogBridge()
        self._worker: AgentWorker | None = None
        self._draft: BugDraft | None = None
        configure_task_dialog(self, "Record Nexus Logs (local + drone)", 760, 780)

        layout = QVBoxLayout(self)

        layout.addWidget(
            make_muted_label(
                f"All selected logs are saved together under:\n"
                f"{LOGS_DIR}/<timestamp>/\n"
                "Use one recording session for cave + drone investigation."
            )
        )

        layout.addWidget(make_section_title("Local (cave)"))
        checks_row = QHBoxLayout()
        self.container_checks: dict[str, QCheckBox] = {}
        for name in DEFAULT_CONTAINERS:
            cb = QCheckBox(name)
            cb.setChecked(True)
            self.container_checks[name] = cb
            checks_row.addWidget(cb)
        checks_row.addStretch()
        layout.addLayout(checks_row)

        layout.addWidget(make_section_title("Drone (platform-manager via SSH)"))
        self.drone_enabled = QCheckBox("Include drone logs in the same folder")
        self.drone_enabled.toggled.connect(self._on_drone_toggled)
        layout.addWidget(self.drone_enabled)

        self.drone_form_widget = QWidget()
        drone_form = QFormLayout(self.drone_form_widget)
        self.drone_host = QLineEdit()
        self.drone_user = QLineEdit()
        self.drone_password = PasswordLineEdit()
        self._load_drone_defaults()
        drone_form.addRow("Host:", self.drone_host)
        drone_form.addRow("User:", self.drone_user)
        drone_form.addRow("Password:", self.drone_password)
        layout.addWidget(self.drone_form_widget)
        layout.addWidget(make_muted_label("Drone password is not saved — enter it each session."))

        btn_row = QHBoxLayout()
        self.test_drone_btn = make_secondary_button("Test Drone Connection")
        self.test_drone_btn.clicked.connect(self._on_test_drone)
        self.start_btn = make_primary_button("Start Recording")
        self.stop_btn = make_secondary_button("Stop Recording")
        self.open_folder_btn = make_secondary_button("Open Logs Folder")
        self.open_folder_btn.clicked.connect(self._on_open_folder)
        self.stop_btn.setEnabled(False)
        self.start_btn.clicked.connect(self._on_start)
        self.stop_btn.clicked.connect(self._on_stop)
        btn_row.addWidget(self.test_drone_btn)
        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.stop_btn)
        btn_row.addWidget(self.open_folder_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.status = make_muted_label("")
        self._status_bridge.line.connect(self._append_status)
        layout.addWidget(self.status)

        layout.addWidget(make_section_title("Analyze & Create Bug"))
        layout.addWidget(
            make_muted_label(
                "אחרי Stop Recording — תאר את הבעיה, נתח לוגים, ואז Open Bug עם הטיוטה והלוגים."
            )
        )
        self.problem_description = QTextEdit()
        self.problem_description.setPlaceholderText(
            "תאר את הבעיה שראית בזמן ההקלטה.\n"
            "לדוגמה: רחפן חוצה אזור אסור / חיבור GCS נופל / mission לא מתחילה"
        )
        self.problem_description.setMaximumHeight(90)
        layout.addWidget(self.problem_description)

        analyze_row = QHBoxLayout()
        self.analyze_btn = make_primary_button("Analyze Logs")
        self.analyze_btn.clicked.connect(self._on_analyze)
        self.open_bug_btn = make_secondary_button("Open Bug")
        self.open_bug_btn.clicked.connect(self._on_open_bug)
        self.open_bug_btn.setEnabled(False)
        analyze_row.addWidget(self.analyze_btn)
        analyze_row.addWidget(self.open_bug_btn)
        analyze_row.addStretch()
        layout.addLayout(analyze_row)

        self.analysis_preview = make_log_view(min_height=140)
        self.analysis_preview.setPlaceholderText("ניתוח הלוגים וטיוטת הבאג יופיעו כאן…")
        layout.addWidget(self.analysis_preview, stretch=1)

        self.analyze_status = make_muted_label("")
        layout.addWidget(self.analyze_status)

        add_dialog_footer(layout, self)
        self._on_drone_toggled(self.drone_enabled.isChecked())

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._sync_state()

    def _on_drone_toggled(self, enabled: bool) -> None:
        self.drone_form_widget.setEnabled(enabled)
        self.test_drone_btn.setEnabled(enabled)

    def _is_recording(self) -> bool:
        return self.services.local_recorder.recording or self.services.drone_recorder.recording

    def _active_recording_dir(self) -> Path | None:
        local_dir = self.services.local_recorder.recording_dir
        drone_dir = self.services.drone_recorder.recording_dir
        if local_dir:
            return local_dir
        if drone_dir:
            return drone_dir
        if app_state.last_recording_path and app_state.last_recording_path.is_dir():
            return app_state.last_recording_path
        return None

    def _has_log_files(self, path: Path | None) -> bool:
        return bool(path and path.is_dir() and any(path.glob("*.log")))

    def _sync_state(self) -> None:
        recording = self._is_recording()
        self.start_btn.setEnabled(not recording)
        self.stop_btn.setEnabled(recording)
        self.drone_enabled.setEnabled(not recording)
        for cb in self.container_checks.values():
            cb.setEnabled(not recording)
        self.drone_form_widget.setEnabled(self.drone_enabled.isChecked() and not recording)
        self.test_drone_btn.setEnabled(self.drone_enabled.isChecked() and not recording)

        active_dir = self._active_recording_dir()
        if active_dir:
            self._show_recording_path(active_dir)

        busy = self._worker is not None and self._worker.isRunning()
        can_analyze = (not recording) and self._has_log_files(active_dir) and not busy
        self.analyze_btn.setEnabled(can_analyze)
        self.problem_description.setEnabled(not recording and not busy)
        self.open_bug_btn.setEnabled(
            (not recording) and (not busy) and self._draft is not None and self._has_log_files(active_dir)
        )

    def _show_recording_path(self, path: Path) -> None:
        log_files = sorted(p.name for p in path.glob("*.log"))
        files_text = ", ".join(log_files) if log_files else "(recording — files appear as logs stream)"
        self.status.setText(f"Folder: {path}\nFiles: {files_text}")

    def _append_status(self, msg: str) -> None:
        active_dir = self._active_recording_dir()
        if active_dir:
            self._show_recording_path(active_dir)
        else:
            self.status.setText(msg)

    def _on_open_folder(self) -> None:
        path = self._active_recording_dir() or LOGS_DIR
        ok, message = reveal_in_file_manager(path)
        if not ok:
            QMessageBox.warning(
                self,
                "Open Folder",
                f"Could not open folder.\n{message}\n\nLogs base path:\n{LOGS_DIR}",
            )

    def _load_drone_defaults(self) -> None:
        drones = self.services.config.get("drones") or []
        if drones:
            d = drones[0]
            self.drone_host.setText(str(d.get("host", "")))
            self.drone_user.setText(str(d.get("user", "")))

    def _save_drone_profile(self) -> None:
        host = self.drone_host.text().strip()
        user = self.drone_user.text().strip()
        if not host:
            return
        self.services.config["drones"] = [{"name": host, "host": host, "user": user}]
        save_config(self.services.config)

    def _drone_credentials(self) -> tuple[str, str, str] | None:
        host = self.drone_host.text().strip()
        user = self.drone_user.text().strip()
        password = self.drone_password.text()
        if not host or not user:
            QMessageBox.information(self, "Input Required", "Enter drone host and user.")
            return None
        if not password:
            QMessageBox.information(self, "Input Required", "Enter the drone SSH password.")
            return None
        return host, user, password

    def _on_test_drone(self) -> None:
        creds = self._drone_credentials()
        if creds is None:
            return
        host, user, password = creds
        ok, message = DroneLogRecorder.test_connection(host, user, password)
        self._status_bridge.line.emit(message)
        if ok:
            self._save_drone_profile()
        else:
            QMessageBox.warning(self, "SSH Failed", message)

    def _on_start(self) -> None:
        selected = [name for name, cb in self.container_checks.items() if cb.isChecked()]
        include_drone = self.drone_enabled.isChecked()
        if not selected and not include_drone:
            QMessageBox.information(
                self,
                "Select Sources",
                "Select at least one local container and/or enable drone logs.",
            )
            return

        drone_creds: tuple[str, str, str] | None = None
        if include_drone:
            drone_creds = self._drone_credentials()
            if drone_creds is None:
                return

        try:
            recording_dir = new_recording_dir()
            app_state.set_recording_path(recording_dir)
            self._draft = None
            self.analysis_preview.clear()
            self.analyze_status.setText("")
            self.open_bug_btn.setEnabled(False)

            if selected:
                self.services.local_recorder.start(
                    selected,
                    on_status=self._append_status,
                    recording_dir=recording_dir,
                )

            if include_drone and drone_creds:
                host, user, password = drone_creds
                self.services.drone_recorder.start(
                    host,
                    user,
                    password,
                    on_status=self._append_status,
                    recording_dir=recording_dir,
                )
                self._save_drone_profile()

            self._show_recording_path(recording_dir)
            self._sync_state()
            self.services.notify_recording_changed()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Recording Error", str(exc))
            self._sync_state()

    def _on_stop(self) -> None:
        local = self.services.local_recorder
        drone = self.services.drone_recorder
        path: Path | None = None

        if local.recording:
            path = local.stop(on_status=self._status_bridge.line.emit)
        if drone.recording:
            drone_path = drone.stop(on_status=self._status_bridge.line.emit)
            path = drone_path or path

        if path:
            app_state.set_recording_path(path)
            self._show_recording_path(path)

        self._sync_state()
        self.services.notify_recording_changed()

    def _require_api_key(self) -> str | None:
        api_key = get_cursor_api_key(self.services.config)
        if not api_key:
            QMessageBox.warning(self, "API Key Required", "הגדר Cursor API Key ב-File → Settings")
            return None
        return api_key

    def _on_analyze(self) -> None:
        if self._is_recording():
            QMessageBox.information(self, "Still Recording", "עצור הקלטה לפני ניתוח לוגים.")
            return

        log_dir = self._active_recording_dir()
        if not self._has_log_files(log_dir):
            QMessageBox.information(
                self,
                "No Logs",
                "אין קבצי לוג. הקלט לוגים קודם (Start → Stop).",
            )
            return

        description = self.problem_description.toPlainText().strip()
        if not description:
            QMessageBox.information(self, "קלט נדרש", "תאר את הבעיה שראית.")
            return

        assert log_dir is not None
        api_key = self._require_api_key()
        if not api_key:
            return

        if self._worker is not None and self._worker.isRunning():
            QMessageBox.information(self, "עסוק", "ניתוח כבר רץ.")
            return

        self._draft = build_local_draft_from_description(description)
        self.analysis_preview.setPlainText(self._draft.to_markdown())
        self.analyze_status.setText("מנתח לוגים…")
        self.analyze_btn.setEnabled(False)
        self.open_bug_btn.setEnabled(False)
        self.problem_description.setEnabled(False)

        prompt = build_log_investigation_prompt(description, log_dir)
        model = get_cursor_model(self.services.config)
        cloud_repo = get_cloud_repo_url(self.services.config)
        self._worker = AgentWorker(
            prompt,
            api_key,
            model,
            cloud_repo,
            fast=True,
            local=True,
            parent=self,
        )
        self._worker.chunk.connect(self._on_analyze_chunk)
        self._worker.finished_ok.connect(self._on_analyze_ok)
        self._worker.finished_err.connect(self._on_analyze_err)
        self._worker.start()

    def _on_analyze_chunk(self, text: str) -> None:
        cursor = self.analysis_preview.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(text)

    def _on_analyze_ok(self, result: str) -> None:
        description = self.problem_description.toPlainText().strip()
        data = parse_bug_draft(result)
        if data:
            agent_draft = BugDraft.from_dict(data)
            draft = self._draft or BugDraft()
            for field in ("summary", "steps_to_reproduce", "expected_result", "actual_result"):
                value = getattr(agent_draft, field, "").strip()
                if value:
                    setattr(draft, field, value)
            if agent_draft.duplicate_warning:
                draft.duplicate_warning = agent_draft.duplicate_warning
            self._draft = enrich_draft_from_description(description, draft)
        else:
            self._draft = enrich_draft_from_description(description, self._draft or BugDraft())

        assert self._draft is not None
        self.analysis_preview.setPlainText(self._draft.to_markdown())
        if self._draft.is_complete():
            self.analyze_status.setText("ניתוח הושלם — בדוק את הטיוטה ולחץ Open Bug")
        else:
            self.analyze_status.setText("ניתוח חלקי — השלם בחלון יצירת באג לפני Open Bug")
        self._sync_state()

    def _on_analyze_err(self, error: str) -> None:
        self.analyze_status.setText("ניתוח נכשל")
        QMessageBox.critical(self, "שגיאת ניתוח", error)
        self._sync_state()

    def _on_open_bug(self) -> None:
        if self._draft is None:
            QMessageBox.information(self, "טיוטה נדרשת", "נתח לוגים קודם (Analyze Logs).")
            return

        log_dir = self._active_recording_dir()
        if not self._has_log_files(log_dir):
            QMessageBox.information(self, "No Logs", "אין קבצי לוג לצרף לבאג.")
            return

        parent = self.parent()
        open_fn = getattr(parent, "open_create_from_logs", None)
        if not callable(open_fn):
            QMessageBox.warning(self, "Open Bug", "לא ניתן לפתוח את דיאלוג יצירת הבאג.")
            return

        assert log_dir is not None
        open_fn(
            description=self.problem_description.toPlainText().strip(),
            draft=self._draft,
            log_dir=log_dir,
        )
