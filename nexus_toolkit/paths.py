"""Dynamic paths resolved per user machine."""

from pathlib import Path

HOME = Path.home()
TOOLKIT_DIR = Path(__file__).resolve().parent.parent
SKILLS_DIR = TOOLKIT_DIR / "skills"
CONFIG_DIR = HOME / ".config" / "nexus-toolkit"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
DEPLOY_MANAGER = HOME / "DeployManager" / "DeployManagerv1.0.1"
COMPOSE_FILE = Path("/opt/ras/docker-compose.yml")
NEXUS_DB_DIR = Path("/opt/ras/db/nexus-core")
NEXUS_DB_FILE = NEXUS_DB_DIR / "nexus.db"
FRONTEND_APP_DIR_LEGACY = HOME / "ras-nexus-front" / "apps" / "app-tactical"
FRONTEND_APP_DIR_NEXUS = HOME / "nexus" / "ras-nexus-front" / "apps" / "app-tactical"
# Prefer the newer ~/nexus/... layout; fall back to the legacy home path.
FRONTEND_APP_DIR_CANDIDATES = (FRONTEND_APP_DIR_NEXUS, FRONTEND_APP_DIR_LEGACY)
FRONTEND_APP_DIR = FRONTEND_APP_DIR_NEXUS
NEXUS_TESTS_DIR = HOME / "nexus" / "nexus-tests"
NEXUS_TESTS_GIT = "git@github.com:RAS-NeuRobotix/nexus-tests.git"
LOGS_DIR = HOME / "nexus-toolkit-logs"
JIRA_BROWSE_BASE = "https://dominionx.atlassian.net/browse"

DEFAULT_CONTAINERS = ("pp3d", "gcs", "nexus-core")


def is_frontend_app_dir(path: Path) -> bool:
    return path.is_dir() and (path / "package.json").is_file()


def resolve_frontend_app_dir(config: dict | None = None) -> Path:
    """Pick a usable Front app dir: config override, then ~/nexus/..., then legacy ~/..."""
    frontend_cfg = (config or {}).get("frontend") or {}
    configured = str(frontend_cfg.get("app_dir") or "").strip()
    if configured:
        configured_path = Path(configured).expanduser()
        if is_frontend_app_dir(configured_path):
            return configured_path

    for candidate in FRONTEND_APP_DIR_CANDIDATES:
        if is_frontend_app_dir(candidate):
            return candidate

    if configured:
        return Path(configured).expanduser()
    return FRONTEND_APP_DIR_CANDIDATES[0]
