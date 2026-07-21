"""Cursor SDK agent integration."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from nexus_toolkit.services.cursor_sdk_patch import apply_cursor_sdk_patches

apply_cursor_sdk_patches()

from nexus_toolkit.paths import SKILLS_DIR
from nexus_toolkit.services.mcp_config import (
    atlassian_mcp_status,
    build_jira_agent_options,
    build_local_analysis_options,
)
from nexus_toolkit.utils import (
    format_log_excerpts,
    is_hebrew_text,
    read_log_excerpts_for_analysis,
)


def _load_skill() -> str:
    skill_path = SKILLS_DIR / "jira" / "SKILL.md"
    if skill_path.exists():
        return skill_path.read_text(encoding="utf-8")
    return ""


def build_search_prompt(description: str, *, fast: bool = False) -> str:
    if fast:
        return _build_fast_search_prompt(description)
    return _build_full_search_prompt(description)


def _build_fast_search_prompt(description: str) -> str:
    if is_hebrew_text(description):
        language_rule = "Return the entire report in Hebrew only."
    else:
        language_rule = "Return the entire report in English."

    return f"""Quick Jira duplicate check — project NEX, dominionx.atlassian.net.
{language_rule}
Speed is critical: minimal MCP calls only.

Bug description:
{description}

Do exactly this:
1. getAccessibleAtlassianResources → cloudId
2. ONE searchJiraIssuesUsingJql (never pass fields), maxResults 10:
   project = NEX AND issuetype = Bug AND text ~ "KEYWORDS" ORDER BY updated DESC
3. Stop. Do NOT call getJiraIssue. Do NOT run more JQL. Do NOT search the codebase.

Report format:
## תוצאת בדיקת Jira
**תיאור:** [one line]
**מסקנה:** כפילות | ריגרסיה | באג חדש | לא ברור

### התאמות שנמצאו
| Key | Status | Resolved | Similarity |
(up to 5 rows — use search result fields only)

### ניתוח
(max 2 short bullet points, plain language, no JQL/code)

### המלצה
(max 2 bullet points with clear action)

No Link column. No internal narration ("אתחיל", "מרחיב חיפוש").
"""


def _build_full_search_prompt(description: str) -> str:
    skill = _load_skill()
    if is_hebrew_text(description):
        language_rule = (
            "IMPORTANT: The user wrote in Hebrew. Return the entire report in Hebrew only "
            "(תיאור, מסקנה, ניתוח, המלצה — הכל בעברית). "
            "Issue keys (NEX-XXX) stay as-is."
        )
    else:
        language_rule = "Respond in English using the skill report template."

    format_rule = """
OUTPUT FORMAT (strict — for on-screen display):
- Matches table columns ONLY: Key | Status | Resolved | Similarity (or Hebrew equivalents).
  Do NOT include a Link column — keys are clickable in the UI.
- **ניתוח / Analysis:** MAX 3 short bullet points (one line each). Plain language only.
  No JQL query text, no code/file names, no long paragraphs.
- **המלצה / Recommendation:** MAX 3 bullet lines, each starting with a clear action verb.
- **מסקנה / Verdict:** one short line (כפילות | ריגרסיה | באג חדש | לא ברור).
- Skip internal reasoning ("אתחיל בבדיקה", "מרחיב חיפוש") — output the final report only.
"""

    return f"""Follow the Jira bug check workflow in this skill:

{skill}

---

{language_rule}
{format_rule}

/jira

{description}

Execute the full workflow:
1. Extract keywords
2. Run 3 JQL queries via Atlassian MCP (project=NEX, dominionx.atlassian.net)
3. Enrich top matches
4. Classify: duplicate / regression / new bug / unclear
5. Return the report using the format rules above
"""


_BUG_DRAFT_JSON_EXAMPLE = """{
  "summary": "One-line bug title in English",
  "steps_to_reproduce": "1. Plan a mission crossing a no-fly zone\\n2. Start the flight\\n3. Observe the drone crosses the forbidden area",
  "expected_result": "System blocks the mission or shows a clear error before flight.",
  "actual_result": "Mission starts and drone crosses the forbidden zone.",
  "duplicate_warning": null,
  "needs_more_info": false,
  "info_request_he": null
}"""


def _generate_prompt_rules(description: str) -> str:
    hebrew = is_hebrew_text(description)
    source_note = (
        "The user wrote in HEBREW — possibly just ONE sentence. "
        "You MUST infer steps, expected, and actual from that sentence. Translate to English."
        if hebrew
        else "The user may write only ONE sentence — infer steps, expected, and actual from it."
    )

    return f"""
Return ONLY valid JSON (no markdown fences). Schema:
{_BUG_DRAFT_JSON_EXAMPLE}

The user provides a FREE-TEXT bug description — NOT a structured form.
They may write only a single sentence (e.g. "רחפן חוצה אזור אסור בזמן טיסה").
{source_note}

You MUST complete the entire form:
- summary: concise English bug title.
- steps_to_reproduce: 3–5 numbered steps that logically lead to this bug (infer from context).
  Do NOT include "open Nexus" or "connect drone" — the drone is always connected.
- expected_result: what SHOULD happen in a correct system.
- actual_result: what ACTUALLY happens (usually the user's symptom).

NEVER return empty steps_to_reproduce, expected_result, or actual_result.
NEVER set needs_more_info unless the input is literally meaningless (e.g. "bug").

Optional: quick duplicate check via Atlassian MCP → duplicate_warning if likely match.
"""


def build_generate_prompt(description: str, log_dir: Optional[Path] = None) -> str:
    rules = _generate_prompt_rules(description)
    user_block = f"""
=== USER DESCRIPTION (your only source for steps / expected / actual) ===
{description}
=== END USER DESCRIPTION ===
"""
    if log_dir and log_dir.is_dir():
        excerpts = read_log_excerpts_for_analysis(log_dir)
        log_block = format_log_excerpts(excerpts)
        return f"""Generate a structured Jira bug draft.
{rules}
{user_block}

Additional context — log excerpts (use only to enrich actual_result / steps):
{log_block}
"""

    return f"""Generate a structured Jira bug draft.
{rules}
{user_block}
"""


def build_log_investigation_prompt(description: str, log_dir: Path) -> str:
    """Analyze recorded logs for a reported problem and produce a Jira bug draft."""
    rules = _generate_prompt_rules(description)
    excerpts = read_log_excerpts_for_analysis(log_dir)
    log_block = format_log_excerpts(excerpts) or "(no .log files found)"
    return f"""Investigate recorded Nexus logs for the reported problem and generate a structured Jira bug draft.
{rules}

=== USER-REPORTED PROBLEM ===
{description}
=== END USER-REPORTED PROBLEM ===

Search the log excerpts below for errors, warnings, stack traces, and events that match the reported problem.
When filling the draft:
- Prefer concrete evidence from the logs in actual_result (container name, timestamps, error lines when available).
- Infer steps_to_reproduce from the user report + log chronology.
- Keep expected_result as correct system behavior.
- Do NOT call external tools or MCP. Use only the user report and log excerpts below.
- Return ONLY the JSON object (no prose, no markdown fences).

Log excerpts:
{log_block}
"""


def build_open_bug_prompt(
    summary: str,
    steps: str,
    expected: str,
    actual: str,
    attach_zip: Optional[Path] = None,
) -> str:
    attach_note = ""
    if attach_zip and attach_zip.is_file():
        attach_note = f"""
After creating the issue, attach this log archive to the bug via Atlassian MCP:
{attach_zip}
"""

    return f"""Create a Jira bug in project NEX via Atlassian MCP (createJiraIssue):
- cloudId: dominionx.atlassian.net (resolve via getAccessibleAtlassianResources if needed)
- issueType: Bug
- summary: {summary}
- description (markdown, English) — ALL sections are mandatory, do not leave empty:
  ## Steps to Reproduce
  {steps or "(not provided)"}

  ## Expected Result
  {expected or "(not provided)"}

  ## Actual Result
  {actual or "(not provided)"}
- Reporter: the currently authenticated Atlassian user
{attach_note}
Return the issue key (NEX-XXX) and browse URL only.
"""


def _format_run_failure(result) -> str:
    detail = (getattr(result, "result", None) or "").strip()
    run_id = getattr(result, "id", "unknown")
    if detail:
        return f"Agent run failed: {run_id}\n{detail}"
    return (
        f"Agent run failed: {run_id}\n"
        "No details from agent. Common causes: prompt too large, API/model issue, "
        "or cloud/local runtime failure. Try again or check File → Settings."
    )


def run_agent_prompt(
    prompt: str,
    api_key: str,
    model: str,
    cloud_repo_url: str,
    on_chunk: Optional[Callable[[str], None]] = None,
    *,
    fast: bool = False,
    local: bool = False,
) -> str:
    from cursor_sdk import Agent, CursorAgentError

    if local:
        options = build_local_analysis_options(api_key, model)
        if on_chunk:
            on_chunk("[ניתוח לוגים מקומי — ללא Jira MCP...]\n\n")
    else:
        ok, mcp_hint = atlassian_mcp_status()
        options = build_jira_agent_options(api_key, model, cloud_repo_url)

        if not ok and on_chunk:
            on_chunk(f"\n[אזהרה: {mcp_hint}]\n\n")
        elif on_chunk:
            if fast:
                on_chunk("[חיפוש מהיר — שאילתת JQL אחת, ~20–40 שניות...]\n\n")
            else:
                on_chunk("[חיפוש מלא — 3 שאילתות JQL + העשרה, ~דקה...]\n\n")

    try:
        if fast or local:
            result = Agent.prompt(prompt, options)
            if result.status == "error":
                raise RuntimeError(_format_run_failure(result))
            text = result.result or ""
            if on_chunk and text:
                on_chunk(text)
            return text

        with Agent.create(options) as agent:
            run = agent.send(prompt)
            collected: list[str] = []
            for message in run.messages():
                if message.type == "assistant":
                    for block in message.message.content:
                        if block.type == "text" and block.text:
                            collected.append(block.text)
                            if on_chunk:
                                on_chunk(block.text)
            result = run.wait()
            if result.status == "error":
                raise RuntimeError(_format_run_failure(result))
            return "".join(collected)
    except CursorAgentError as exc:
        raise RuntimeError(str(exc)) from exc


def validate_api_key(api_key: str) -> tuple[bool, str]:
    if not api_key:
        return False, "Cursor API key is not configured."
    try:
        from cursor_sdk import Cursor

        models = Cursor.models.list(api_key=api_key)
        if models:
            return True, f"Connected ({len(models)} models available)"
        return True, "Connected"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
