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
FRONTEND_APP_DIR = HOME / "ras-nexus-front" / "apps" / "app-tactical"
NEXUS_TESTS_DIR = HOME / "nexus-tests"
NEXUS_TESTS_GIT = "git@github.com:RAS-NeuRobotix/nexus-tests.git"
LOGS_DIR = HOME / "nexus-toolkit-logs"
JIRA_BROWSE_BASE = "https://dominionx.atlassian.net/browse"

DEFAULT_CONTAINERS = ("pp3d", "gcs", "nexus-core")
