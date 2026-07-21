"""Load Atlassian MCP configuration for Cursor SDK cloud agents."""

from __future__ import annotations

import json
from pathlib import Path

from cursor_sdk import (
    AgentOptions,
    CloudAgentOptions,
    CloudRepository,
    HttpMcpServerConfig,
    LocalAgentOptions,
)

CURSOR_MCP_FILE = Path.home() / ".cursor" / "mcp.json"
ATLASSIAN_MCP_URL = "https://mcp.atlassian.com/v1/mcp/authv2"
DEFAULT_CLOUD_REPO = "https://github.com/RAS-NeuRobotix/ras-nexus-back"


def cursor_mcp_file_exists() -> bool:
    return CURSOR_MCP_FILE.is_file()


def load_atlassian_mcp_url() -> str | None:
    """Return the Atlassian MCP URL from ~/.cursor/mcp.json if configured."""
    if not CURSOR_MCP_FILE.is_file():
        return None

    try:
        data = json.loads(CURSOR_MCP_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    for name, cfg in (data.get("mcpServers") or {}).items():
        if not isinstance(cfg, dict) or not cfg.get("url"):
            continue
        if name.lower().find("atlassian") >= 0 or "atlassian" in str(cfg["url"]).lower():
            return str(cfg["url"])
    return None


def has_atlassian_mcp_configured() -> bool:
    return load_atlassian_mcp_url() is not None


def atlassian_mcp_status() -> tuple[bool, str]:
    """Return whether Atlassian MCP is likely available and a user-facing hint."""
    if not cursor_mcp_file_exists():
        return False, (
            "לא נמצא ~/.cursor/mcp.json — הגדר Atlassian MCP ב-Cursor IDE "
            "(Settings → MCP) ואז התחבר דרך OAuth."
        )

    if not has_atlassian_mcp_configured():
        return False, (
            "Atlassian MCP לא מוגדר ב-~/.cursor/mcp.json. "
            "הוסף אותו ב-Cursor IDE → Settings → MCP."
        )

    return True, (
        "Atlassian MCP מוגדר. חיפוש/יצירת באגים רצים דרך Cloud Agent "
        "(דורש חיבור אינטרנט). ודא ש-Atlassian מאומת ב-Cursor IDE → MCP "
        "או ב-Cursor Dashboard → Integrations."
    )


def build_jira_agent_options(
    api_key: str,
    model: str,
    cloud_repo_url: str,
) -> AgentOptions:
    """Build a cloud AgentOptions with Atlassian MCP for Jira workflows.

    Local SDK agents do not receive OAuth MCP tools in standalone apps.
    Cloud agents reuse Atlassian OAuth from the user's Cursor account.
    """
    mcp_url = load_atlassian_mcp_url() or ATLASSIAN_MCP_URL
    return AgentOptions(
        api_key=api_key,
        model=model,
        cloud=CloudAgentOptions(
            repos=[CloudRepository(url=cloud_repo_url)],
            skip_reviewer_request=True,
        ),
        mcp_servers={
            "Atlassian-MCP-Server": HttpMcpServerConfig(url=mcp_url),
        },
    )


def build_local_analysis_options(api_key: str, model: str, cwd: str | Path | None = None) -> AgentOptions:
    """Local agent for log analysis — no Atlassian MCP required."""
    workdir = Path(cwd) if cwd is not None else Path.home()
    return AgentOptions(
        api_key=api_key,
        model=model,
        local=LocalAgentOptions(cwd=str(workdir)),
    )
