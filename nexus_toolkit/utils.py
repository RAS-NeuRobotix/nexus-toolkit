"""Utility helpers."""

from __future__ import annotations

import json
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from nexus_toolkit.paths import LOGS_DIR

LOG_TAIL_LINES = 500
ANALYSIS_TAIL_LINES = 120
ANALYSIS_MAX_CHARS_PER_FILE = 12_000
ANALYSIS_MAX_TOTAL_CHARS = 48_000
MAX_ZIP_BYTES = 10 * 1024 * 1024

_ERROR_LINE_RE = re.compile(
    r"(error|exception|traceback|failed|fatal|panic|critical|warn(?:ing)?)",
    re.IGNORECASE,
)


def new_recording_dir() -> Path:
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = LOGS_DIR / stamp
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_log_tails(directory: Path, max_lines: int = LOG_TAIL_LINES) -> dict[str, str]:
    excerpts: dict[str, str] = {}
    if not directory.is_dir():
        return excerpts
    for log_file in sorted(directory.glob("*.log")):
        try:
            lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
            tail = "\n".join(lines[-max_lines:])
            excerpts[log_file.name] = tail
        except OSError:
            excerpts[log_file.name] = "(failed to read file)"
    return excerpts


def _trim_excerpt(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def read_log_excerpts_for_analysis(
    directory: Path,
    *,
    max_lines: int = ANALYSIS_TAIL_LINES,
    max_chars_per_file: int = ANALYSIS_MAX_CHARS_PER_FILE,
    max_total_chars: int = ANALYSIS_MAX_TOTAL_CHARS,
) -> dict[str, str]:
    """Compact excerpts for agent prompts — recent lines + errors, hard size budget."""
    excerpts: dict[str, str] = {}
    if not directory.is_dir():
        return excerpts

    remaining = max_total_chars
    for log_file in sorted(directory.glob("*.log")):
        if remaining <= 0:
            excerpts[log_file.name] = "(truncated — prompt size limit)"
            continue
        try:
            lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            excerpts[log_file.name] = "(failed to read file)"
            continue

        if not lines:
            excerpts[log_file.name] = "(empty)"
            continue

        tail = lines[-max_lines:]
        interesting = [line for line in lines if _ERROR_LINE_RE.search(line)]
        # Prefer recent interesting lines, then fill with plain tail.
        selected: list[str] = []
        seen: set[str] = set()
        for line in interesting[-max_lines // 2 :] + tail:
            if line in seen:
                continue
            seen.add(line)
            selected.append(line)

        file_budget = min(max_chars_per_file, remaining)
        text = _trim_excerpt("\n".join(selected), file_budget)
        excerpts[log_file.name] = text
        remaining -= len(text)

    return excerpts


def format_log_excerpts(excerpts: dict[str, str]) -> str:
    if not excerpts:
        return "(no log files found)"
    parts = []
    for name, content in excerpts.items():
        parts.append(f"### {name}\n{content}")
    return "\n\n".join(parts)


def zip_recording(directory: Path, max_bytes: int = MAX_ZIP_BYTES) -> Optional[Path]:
    if not directory.is_dir():
        return None
    zip_path = directory.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in directory.rglob("*"):
            if file_path.is_file():
                archive.write(file_path, arcname=file_path.relative_to(directory))
    if zip_path.stat().st_size > max_bytes:
        zip_path.unlink(missing_ok=True)
        return _zip_error_lines_only(directory, max_bytes)
    return zip_path


def _zip_error_lines_only(directory: Path, max_bytes: int) -> Optional[Path]:
    zip_path = directory.with_name(directory.name + "_errors.zip")
    error_pattern = re.compile(r"error|exception|fatal|traceback", re.IGNORECASE)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for log_file in directory.glob("*.log"):
            try:
                filtered = [
                    line
                    for line in log_file.read_text(encoding="utf-8", errors="replace").splitlines()
                    if error_pattern.search(line)
                ]
                if filtered:
                    archive.writestr(
                        log_file.name,
                        "\n".join(filtered[-LOG_TAIL_LINES:]),
                    )
            except OSError:
                continue
    if not zip_path.exists() or zip_path.stat().st_size == 0:
        return None
    if zip_path.stat().st_size > max_bytes:
        zip_path.unlink(missing_ok=True)
        return None
    return zip_path


def parse_bug_draft_json(text: str) -> Optional[dict]:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


_SECTION_ALIASES: dict[str, str] = {
    "summary": "summary",
    "steps to reproduce": "steps_to_reproduce",
    "steps": "steps_to_reproduce",
    "expected result": "expected_result",
    "expected": "expected_result",
    "actual result": "actual_result",
    "actual": "actual_result",
}


def parse_bug_draft_markdown(text: str) -> dict:
    """Parse ## section headers from agent markdown output."""
    data: dict[str, str] = {}
    current_key: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer, current_key
        if current_key is not None:
            data[current_key] = "\n".join(buffer).strip()
        buffer = []

    for line in text.splitlines():
        dup = re.search(r"Possible duplicate.*?`(NEX-\d+)`|(NEX-\d+)", line, re.IGNORECASE)
        if dup:
            data["duplicate_warning"] = dup.group(1) or dup.group(2)
            continue
        if line.startswith("## "):
            flush()
            heading = line[3:].strip().lower()
            current_key = _SECTION_ALIASES.get(heading)
            continue
        if current_key is not None:
            buffer.append(line)

    flush()
    return data


def parse_bug_draft(text: str) -> Optional[dict]:
    """Parse bug draft from JSON and/or markdown sections."""
    merged: dict = {}
    json_data = parse_bug_draft_json(text)
    if json_data:
        merged.update(json_data)
    markdown_data = parse_bug_draft_markdown(text)
    for key, value in markdown_data.items():
        if value and not str(merged.get(key, "")).strip():
            merged[key] = value
    return merged or None


def build_missing_fields_message_he(draft) -> str:
    from nexus_toolkit.models import BugDraft

    if not isinstance(draft, BugDraft):
        return "חסר מידע ליצירת באג."

    if draft.info_request_he:
        return draft.info_request_he

    missing = draft.missing_required_labels()
    if not missing:
        return ""

    lines = [
        "לא ניתן למלא את כל שדות הבאג מהתיאור שסיפקת.",
        "",
        "שדות חסרים:",
        *[f"• {label}" for label in missing],
        "",
        "הוסף בתיאור החופשי:",
        "• צעדים לשחזור (מה עושים לפני שהבאג מופיע)",
        "• מה אמור לקרות (Expected)",
        "• מה קורה בפועל (Actual)",
        "",
        "ואז לחץ שוב Generate Bug Draft, או מלא ידנית בפאנל Edit.",
    ]
    return "\n".join(lines)


def shorten_image_ref(image: str) -> str:
    """Display image as name:tag[@digest] — drop registry/path prefix."""
    value = (image or "").strip()
    if not value or value.startswith("("):
        return value
    name_tag, at, digest = value.partition("@")
    short_name = name_tag.rsplit("/", 1)[-1]
    if at and digest:
        return f"{short_name}@{digest}"
    return short_name


def split_image_version_signature(image: str) -> tuple[str, str]:
    """Split image ref into (version/name:tag, signature/sha...)."""
    value = shorten_image_ref(image)
    if not value or value.startswith("("):
        return value, ""

    lower = value.lower()
    if "@sha256:" in lower:
        idx = lower.index("@sha256:")
        return value[:idx], value[idx + 1 :]

    if "@" in value:
        version, _, digest = value.partition("@")
        return version, digest

    marker = "_sha256_"
    if marker in lower:
        idx = lower.index(marker)
        return value[:idx], "sha256_" + value[idx + len(marker) :]

    return value, ""


def extract_issue_key(text: str) -> Optional[str]:
    match = re.search(r"\bNEX-\d+\b", text)
    return match.group(0) if match else None


def is_hebrew_text(text: str) -> bool:
    return bool(re.search(r"[\u0590-\u05FF]", text))


def reveal_in_file_manager(path: Path) -> tuple[bool, str]:
    """Open a directory (or parent of a file) in the system file manager."""
    import shutil
    import subprocess

    target = path.expanduser().resolve()
    if target.is_file():
        target = target.parent
    if not target.is_dir():
        return False, f"Path not found: {target}"

    for command in (["xdg-open", str(target)], ["gio", "open", str(target)]):
        if shutil.which(command[0]):
            try:
                subprocess.Popen(command)
                return True, str(target)
            except OSError as exc:
                return False, str(exc)

    return False, "No file manager launcher found (xdg-open)"

