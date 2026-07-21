# Nexus Toolkit — הרצה

מדריך קצר להפעלת האפליקציה על Ubuntu.

## דרישות

- Python 3.10+
- Docker + `docker compose`
- Azure CLI (`az`) — לעדכון מערכת
- Cursor API Key — ל-Jira (הגדרה ב-**File → Settings** באפליקציה)

---

## התקנה ראשונה (פעם אחת)

```bash
cd ~/ras-nexus-back/tools/nexus-toolkit
python3 -m pip install -r requirements.txt --target vendor
```

החבילות מותקנות לתיקייה `vendor/` ליד האפליקציה — **בלי venv** ובלי לשנות את Python של המערכת.

---

## הרצה

```bash
cd ~/ras-nexus-back/tools/nexus-toolkit
python3 main.py
```

זהו. אין צורך ב-`source .venv/bin/activate`.

---

## עדכון חבילות

אחרי שינוי ב-`requirements.txt`:

```bash
cd ~/ras-nexus-back/tools/nexus-toolkit
python3 -m pip install -r requirements.txt --target vendor --upgrade
```

---

## קיצור דרך בשולחן העבודה (אופציונלי)

```bash
cd ~/ras-nexus-back/tools/nexus-toolkit
chmod +x install-desktop.sh
./install-desktop.sh
```

נוצר קיצור **Nexus Toolkit** בתפריט האפליקציות.

---

## בעיות נפוצות

### `Missing Python packages: cursor-sdk, ...`

הרץ שוב את התקנת ה-vendor:

```bash
cd ~/ras-nexus-back/tools/nexus-toolkit
python3 -m pip install -r requirements.txt --target vendor
```

### `externally-managed-environment` בהתקנה

אל תשתמש ב-`pip install` גלובלי. השתמש רק ב-`--target vendor` כמו למעלה.

### Jira לא עובד / Atlassian MCP

1. פתח **Cursor IDE** → **Settings → MCP** → ודא ש-**Atlassian** מחובר
2. באפליקציה: **File → Settings** → הגדר **Cursor API Key** ו-**Cloud repo**

### לוגים נשמרים ב-

```
~/nexus-toolkit-logs/<timestamp>/
```

---

## מידע נוסף

תיעוד מלא: [README.md](README.md)
