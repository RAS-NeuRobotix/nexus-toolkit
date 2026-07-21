"""Load and save user configuration."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from nexus_toolkit.paths import CONFIG_DIR, CONFIG_FILE

DEFAULT_CONFIG: dict[str, Any] = {
    "cursor": {
        "api_key": "",
        "model": "composer-2.5",
        "cloud_repo": "https://github.com/RAS-NeuRobotix/ras-nexus-back",
    },
    "deploy": {
        "be_version": "main",
        "fe_version": "latest",
        "project": None,
    },
    "drones": [],
    "tests": {
        "repo_dir": str(Path.home() / "nexus-tests"),
        "git_url": "git@github.com:RAS-NeuRobotix/nexus-tests.git",
    },
    "jira": {
        "fast_search": True,
    },
}


def load_config() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        return deepcopy(DEFAULT_CONFIG)
    with CONFIG_FILE.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    merged = deepcopy(DEFAULT_CONFIG)
    for key, value in data.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return merged


def save_config(config: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with CONFIG_FILE.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(config, handle, default_flow_style=False, allow_unicode=True)


def get_cursor_api_key(config: dict[str, Any]) -> str:
    return str(config.get("cursor", {}).get("api_key", "")).strip()


def get_cursor_model(config: dict[str, Any]) -> str:
    return str(config.get("cursor", {}).get("model", "composer-2.5"))


def get_cloud_repo_url(config: dict[str, Any]) -> str:
    from nexus_toolkit.services.mcp_config import DEFAULT_CLOUD_REPO

    return str(config.get("cursor", {}).get("cloud_repo", DEFAULT_CLOUD_REPO)).strip() or DEFAULT_CLOUD_REPO


def get_jira_fast_search(config: dict[str, Any]) -> bool:
    return bool(config.get("jira", {}).get("fast_search", True))
