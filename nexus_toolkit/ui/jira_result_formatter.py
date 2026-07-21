"""Convert agent Jira search markdown into readable HTML for the UI."""

from __future__ import annotations

import html
import re

from nexus_toolkit.paths import JIRA_BROWSE_BASE
from nexus_toolkit.ui.design_system import (
    COLOR_BLUE,
    COLOR_BORDER,
    COLOR_HEADER,
    COLOR_STRONG_BLUE,
    COLOR_SURFACE,
    COLOR_SURFACE_ALT,
    COLOR_TEXT,
    COLOR_TEXT_SOFT,
)
from nexus_toolkit.utils import is_hebrew_text

_ISSUE_KEY = re.compile(r"\bNEX-\d+\b")
_URL = re.compile(r"https?://[^\s<>\"]+")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_CHECKBOX = re.compile(r"^[-*]\s+\[[ xX]\]\s+")
_LINK_COLUMN = re.compile(r"^link$", re.IGNORECASE)
_SECTION_LINE = re.compile(r"^(#{1,3})\s+(.+)$")


def format_jira_report_html(raw: str, *, browse_base: str = JIRA_BROWSE_BASE) -> str:
    """Turn markdown-ish agent output into styled HTML with clickable issue links."""
    if not raw.strip():
        return ""

    blocks: list[str] = []
    lines = raw.splitlines()
    index = 0
    in_list = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            blocks.append("</ul>")
            in_list = False

    while index < len(lines):
        line = lines[index].rstrip()

        if not line.strip():
            close_list()
            index += 1
            continue

        if line.strip().startswith("|") and "|" in line[1:]:
            close_list()
            table_lines: list[str] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_lines.append(lines[index].strip())
                index += 1
            blocks.append(_render_table(table_lines, browse_base))
            continue

        section = _SECTION_LINE.match(line.strip())
        if section:
            close_list()
            level = len(section.group(1))
            title = _inline_markup(section.group(2).strip(), browse_base)
            if level <= 2:
                blocks.append(
                    f'<h2 style="text-align:center;font-size:17pt;font-weight:bold;'
                    f'margin:18px 0 10px;color:{COLOR_STRONG_BLUE};">{title}</h2>'
                )
            else:
                blocks.append(
                    f'<h3 style="text-align:center;font-size:14pt;font-weight:bold;'
                    f'margin:16px 0 8px;color:{COLOR_BLUE};">{title}</h3>'
                )
            index += 1
            continue

        if _CHECKBOX.match(line.strip()):
            if not in_list:
                blocks.append('<ul style="margin:6px 0 12px 24px;line-height:1.5;">')
                in_list = True
            item = _CHECKBOX.sub("", line.strip())
            blocks.append(
                f"<li>{_inline_markup(item, browse_base)}</li>"
            )
            index += 1
            continue

        if line.strip().startswith(("- ", "* ")) and not line.strip().startswith("- ["):
            if not in_list:
                blocks.append('<ul style="margin:6px 0 12px 24px;line-height:1.5;">')
                in_list = True
            item = line.strip()[2:]
            blocks.append(f"<li>{_inline_markup(item, browse_base)}</li>")
            index += 1
            continue

        close_list()
        blocks.append(
            f'<p style="margin:8px 0;line-height:1.65;">'
            f"{_inline_markup(line.strip(), browse_base)}</p>"
        )
        index += 1

    close_list()

    direction = "rtl" if is_hebrew_text(raw) else "ltr"
    align = "right" if direction == "rtl" else "left"
    body = "\n".join(blocks)
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:'Segoe UI',Arial,sans-serif;font-size:11pt;
background:{COLOR_SURFACE};color:{COLOR_TEXT};direction:{direction};text-align:{align};">
{body}
</body>
</html>"""


def extract_issue_keys(text: str) -> list[str]:
    """Return unique NEX issue keys in order of appearance."""
    seen: set[str] = set()
    keys: list[str] = []
    for match in _ISSUE_KEY.finditer(text):
        key = match.group(0)
        if key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def _render_table(table_lines: list[str], browse_base: str) -> str:
    if len(table_lines) < 2:
        return f"<p>{_inline_markup(' '.join(table_lines), browse_base)}</p>"

    def split_row(row: str) -> list[str]:
        return [cell.strip() for cell in row.strip().strip("|").split("|")]

    headers = split_row(table_lines[0])
    keep_indices = [
        index
        for index, header in enumerate(headers)
        if not _LINK_COLUMN.match(header.strip())
    ]
    if not keep_indices:
        keep_indices = list(range(len(headers)))

    headers = [headers[index] for index in keep_indices]
    body_rows = [
        [split_row(row)[index] for index in keep_indices if index < len(split_row(row))]
        for row in table_lines[2:]
        if row.strip() and not re.match(r"^\|?\s*:?-+", row)
    ]

    thead = "".join(
        f'<th style="padding:8px 10px;background:{COLOR_HEADER};color:{COLOR_TEXT_SOFT};'
        f'border:1px solid {COLOR_BORDER};">'
        f"{_inline_markup(h, browse_base, link_keys=False)}</th>"
        for h in headers
    )
    tbody_parts: list[str] = []
    key_col = 0 if headers and headers[0].lower() in {"key", "מפתח"} else None

    for row in body_rows:
        cells: list[str] = []
        for col_index, cell in enumerate(row):
            if key_col is not None and col_index == key_col:
                content = _render_issue_key_cell(cell, browse_base)
            else:
                content = _inline_markup(cell, browse_base, link_keys=True)
            cells.append(
                f'<td style="padding:8px 10px;border:1px solid {COLOR_BORDER};'
                f'background:{COLOR_SURFACE_ALT};vertical-align:top;">'
                f"{content}</td>"
            )
        tbody_parts.append(f"<tr>{''.join(cells)}</tr>")

    return f"""
<table style="width:100%;border-collapse:collapse;margin:10px 0 16px;font-size:10.5pt;">
  <thead><tr>{thead}</tr></thead>
  <tbody>{''.join(tbody_parts)}</tbody>
</table>
"""


def _render_issue_key_cell(cell: str, browse_base: str) -> str:
    key_match = _ISSUE_KEY.search(cell)
    if not key_match:
        return _inline_markup(cell, browse_base, link_keys=True)
    key = key_match.group(0)
    url = f"{browse_base}/{key}"
    return (
        f'<a href="{html.escape(url, quote=True)}" '
        f'style="color:{COLOR_BLUE};font-weight:bold;text-decoration:none;font-size:11pt;">'
        f"{html.escape(key)}</a>"
    )


def _inline_markup(text: str, browse_base: str, *, link_keys: bool = True) -> str:
    segments: list[tuple[str, str]] = []
    last = 0
    for match in _BOLD.finditer(text):
        if match.start() > last:
            segments.append(("text", text[last : match.start()]))
        segments.append(("bold", match.group(1)))
        last = match.end()
    if last < len(text):
        segments.append(("text", text[last:]))

    if not segments:
        segments = [("text", text)]

    parts: list[str] = []
    for kind, content in segments:
        escaped = html.escape(content)
        linked = _linkify_plain(escaped, browse_base, link_keys=link_keys)
        if kind == "bold":
            parts.append(f"<b>{linked}</b>")
        else:
            parts.append(linked)
    return "".join(parts)


def _linkify_plain(escaped_text: str, browse_base: str, *, link_keys: bool = True) -> str:
    placeholders: list[str] = []

    def stash_url(match: re.Match[str]) -> str:
        placeholders.append(match.group(0))
        return f"\x00U{len(placeholders) - 1}\x00"

    text = _URL.sub(stash_url, escaped_text)
    if link_keys:
        text = _ISSUE_KEY.sub(
            lambda match: _issue_anchor(match.group(0), browse_base),
            text,
        )

    for index, url in enumerate(placeholders):
        key_match = _ISSUE_KEY.search(url)
        if key_match and JIRA_BROWSE_BASE.rstrip("/") in url:
            replacement = _issue_anchor(key_match.group(0), browse_base)
        else:
            replacement = (
                f'<a href="{html.escape(url, quote=True)}" '
                f'style="color:{COLOR_BLUE};">{html.escape(url)}</a>'
            )
        text = text.replace(f"\x00U{index}\x00", replacement)
    return text


def _issue_anchor(key: str, browse_base: str) -> str:
    url = f"{browse_base}/{key}"
    return (
        f'<a href="{html.escape(url, quote=True)}" '
        f'style="color:{COLOR_BLUE};font-weight:bold;text-decoration:none;">'
        f"{html.escape(key)}</a>"
    )
