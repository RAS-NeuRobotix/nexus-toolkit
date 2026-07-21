"""Shared UI widget factories."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from nexus_toolkit.ui.design_system import (
    COLOR_MUTED,
    COMPACT_BTN_WIDTH,
    COMPACT_BTN_WIDTH_WIDE,
    DIALOG_HEIGHT,
    DIALOG_WIDTH,
    LAUNCHER_BTN_HEIGHT,
    LAUNCHER_BTN_WIDTH,
    SPACING_MD,
    SPACING_SM,
    STATUS_TABLE_ACTIONS_WIDTH,
    STATUS_TABLE_ROW_HEIGHT,
    bilingual,
    status_color,
)


def configure_task_dialog(
    dialog: QDialog,
    title: str,
    width: int = DIALOG_WIDTH,
    height: int = DIALOG_HEIGHT,
) -> None:
    dialog.setWindowTitle(title)
    dialog.setMinimumSize(width, height)
    dialog.resize(width, height)


def make_page_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("class", "page-title")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return label


def make_subtitle(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("class", "subtitle")
    label.setWordWrap(True)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return label


def make_section_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("class", "section-title")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return label


def make_muted_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("class", "muted")
    label.setWordWrap(True)
    return label


def make_status_row(initial_text: str = "Checking...") -> tuple[QLabel, QLabel]:
    indicator = QLabel("●")
    indicator.setProperty("class", "status-indicator")
    status = QLabel(initial_text)
    return indicator, status


def set_status_indicator(indicator: QLabel, ok: bool, message: str, status: QLabel) -> None:
    status.setText(message)
    indicator.setStyleSheet(f"color: {status_color(ok)}; font-size: 16px;")


def make_launcher_button(hebrew: str, english: str) -> QPushButton:
    btn = QPushButton(bilingual(hebrew, english))
    btn.setProperty("class", "launcher")
    btn.setMinimumSize(LAUNCHER_BTN_WIDTH, LAUNCHER_BTN_HEIGHT)
    return btn


def make_primary_button(text: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setProperty("class", "primary")
    return btn


def make_secondary_button(text: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setProperty("class", "secondary")
    return btn


def make_danger_button(text: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setProperty("class", "danger")
    return btn


def make_compact_button(text: str, *, wide: bool = False) -> QPushButton:
    btn = QPushButton(text)
    btn.setProperty("class", "compact")
    width = COMPACT_BTN_WIDTH_WIDE if wide else COMPACT_BTN_WIDTH
    btn.setFixedWidth(width)
    btn.setFixedHeight(28)
    return btn


def make_log_view(min_height: int = 160) -> QTextEdit:
    log = QTextEdit()
    log.setReadOnly(True)
    log.setMinimumHeight(min_height)
    return log


class PasswordLineEdit(QWidget):
    """Password field with show/hide eye toggle."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._edit = QLineEdit()
        self._edit.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self._edit, stretch=1)

        self._toggle = QToolButton()
        self._toggle.setCheckable(True)
        self._toggle.setProperty("class", "password-toggle")
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._toggle.toggled.connect(self._on_toggled)
        layout.addWidget(self._toggle)
        self._on_toggled(False)

    def _on_toggled(self, visible: bool) -> None:
        if visible:
            self._edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self._toggle.setText("🙈")
            self._toggle.setToolTip("Hide password")
        else:
            self._edit.setEchoMode(QLineEdit.EchoMode.Password)
            self._toggle.setText("👁")
            self._toggle.setToolTip("Show password")

    def text(self) -> str:
        return self._edit.text()

    def setText(self, text: str) -> None:  # noqa: N802 — Qt API
        self._edit.setText(text)

    def setPlaceholderText(self, text: str) -> None:  # noqa: N802 — Qt API
        self._edit.setPlaceholderText(text)

    def setEnabled(self, enabled: bool) -> None:  # noqa: N802 — Qt API
        super().setEnabled(enabled)
        self._edit.setEnabled(enabled)
        self._toggle.setEnabled(enabled)

    def line_edit(self) -> QLineEdit:
        return self._edit


def ask_password(
    parent: QWidget,
    title: str,
    label: str,
) -> tuple[str, bool]:
    """Modal password prompt with show/hide eye. Returns (password, accepted)."""
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setMinimumWidth(420)

    layout = QVBoxLayout(dialog)
    layout.addWidget(make_muted_label(label))
    field = PasswordLineEdit()
    layout.addWidget(field)

    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    field.line_edit().returnPressed.connect(dialog.accept)
    field.line_edit().setFocus()

    if dialog.exec() != QDialog.DialogCode.Accepted:
        return "", False
    return field.text(), True


def configure_status_table(
    table: QTableWidget,
    actions_width: int = STATUS_TABLE_ACTIONS_WIDTH,
) -> None:
    """Configure status table columns: Container | Version | Signature | Status | Actions."""
    header = table.horizontalHeader()
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
    header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
    header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
    header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
    table.setColumnWidth(4, actions_width)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(STATUS_TABLE_ROW_HEIGHT)
    table.setAlternatingRowColors(True)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)


def add_dialog_footer(layout: QVBoxLayout, dialog: QDialog) -> None:
    row = QHBoxLayout()
    row.addStretch()
    close_btn = make_secondary_button("Close")
    close_btn.clicked.connect(dialog.accept)
    row.addWidget(close_btn)
    layout.addLayout(row)


def confirm_action(parent: QWidget, title: str, message: str) -> bool:
    result = QMessageBox.question(
        parent,
        title,
        message,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return result == QMessageBox.StandardButton.Yes
