# Nexus Ubuntu Toolkit

Desktop application for Ubuntu with two tabs:

- **Jira** — search bugs and create bugs via Cursor agent (with optional log analysis)
- **Nexus Control** — update Nexus (DeployManager + docker compose), record logs, version info

## Prerequisites

- Python 3.10+
- Docker and `docker compose`
- Azure CLI (`az`) for system updates
- [DeployManager](DeployManagerv1.0.1) at `~/DeployManager/DeployManagerv1.0.1`
- Nexus stack at `/opt/ras/docker-compose.yml`
- **Cursor API Key** from [Cursor Dashboard → Integrations](https://cursor.com/dashboard/integrations)
## Atlassian MCP (חובה ל-Jira)

פעולות Jira רצות דרך **Cloud Agent** של Cursor (לא Local Agent), כי רק שם Atlassian MCP זמין עם OAuth.

1. פתח **Cursor IDE** → **Settings → MCP** → ודא ש-**Atlassian** מחובר (OAuth)
2. ודא ש-`~/.cursor/mcp.json` מכיל את השרת (למשל `Atlassian-MCP-Server`)
3. ב-**File → Settings** באפליקציה: הגדר **Cloud repo** ל-repo שמחובר ל-GitHub שלך (ברירת מחדל: `RAS-NeuRobotix/ras-nexus-back`)

חיפוש/יצירת באג לוקחים בדרך כלל 30–60 שניות (Cloud Agent).

אם מופיעה הודעה "Atlassian MCP לא זמין" — התחבר מחדש דרך Cursor IDE → MCP.

## Install

**Option A — direct `python3` (recommended on Ubuntu):**

```bash
cd tools/nexus-toolkit
python3 -m pip install -r requirements.txt --target vendor
python3 main.py
```

Dependencies install into `vendor/` next to the app (no venv, no system Python changes).

See **[RUN.md](RUN.md)** for a short Hebrew run guide.

**Option B — virtualenv:**

```bash
cd tools/nexus-toolkit
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## Desktop launcher

```bash
chmod +x install-desktop.sh
./install-desktop.sh
```

Creates `~/.local/share/applications/nexus-toolkit.desktop`.

## Configuration

Stored at `~/.config/nexus-toolkit/config.yaml`:

```yaml
cursor:
  api_key: "cursor_..."
  model: composer-2.5
deploy:
  be_version: main
  fe_version: latest
  project: null
drones:
  - name: "192.168.1.100"
    host: "192.168.1.100"
    user: "pi"
```

SSH password is entered in the dialog only (not saved to config).

## Paths (per user)

| Path | Purpose |
|------|---------|
| `~/DeployManager/DeployManagerv1.0.1` | System update |
| `/opt/ras/docker-compose.yml` | Docker compose |
| `~/nexus-toolkit-logs/` | Recorded logs |
| `~/.config/nexus-toolkit/config.yaml` | Settings |

## Jira workflow

1. **Search** — describe bug, agent runs `/jira` skill via Atlassian MCP
2. **Create** — enter description → optional "Analyze logs" → Generate → Edit → Open Bug
3. **Attach logs** — optional zip attachment on Open Bug (separate from analyze)

## Nexus Control

1. Check Azure login and installed versions
2. **Update System** — `DeployManager download` then `docker compose up -d`
3. **Record logs** — local containers and/or drone in one timestamp folder (`~/nexus-toolkit-logs/<timestamp>/`)
