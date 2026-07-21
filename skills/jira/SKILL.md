---
name: jira
description: >-
  Search NEX Jira for duplicate bugs and regression candidates before opening
  a new ticket. Use when the user invokes /jira or asks to check if a bug
  already exists in Jira.
disable-model-invocation: true
---

# Jira Bug Check (`/jira`)

Check whether a bug already exists in Jira (project **NEX**, `dominionx.atlassian.net`) and classify it as duplicate, regression, or new before opening a ticket.

## Prerequisites

- **Atlassian MCP Server** must be configured in `~/.cursor/mcp.json` and authenticated via OAuth.
- Always read MCP tool schemas before calling tools.

## Workflow

### Step 1 — Collect bug description

If the user invoked `/jira` without a description, ask for:
- Symptoms (what happens vs. what should happen)
- Affected service / component / screen
- Steps to reproduce (if known)
- Error messages or logs

Respond in the same language the user writes in.

### Step 2 — Extract search terms

From the description, extract **3–6 keywords** for JQL:
- Service names (e.g. `safety-critical-manager`, `nexus-core`)
- Class / file names (e.g. `NexusCoreMapDtmClient`)
- Error text, endpoints, UI labels

Build a `text ~ "term1 term2 term3"` clause. Escape double quotes inside terms.

### Step 3 — Resolve cloudId

Call `getAccessibleAtlassianResources` and pick the resource for `dominionx.atlassian.net`. Use its `id` as `cloudId` in all subsequent calls.

### Step 4 — Search Jira (parallel)

Run these three JQL queries via `searchJiraIssuesUsingJql`. **Never pass the `fields` parameter** — it breaks in this runtime.

```jql
project = NEX AND issuetype = Bug AND status NOT IN (Done, Closed, Resolved) AND text ~ "KEYWORDS" ORDER BY updated DESC
```

```jql
project = NEX AND issuetype = Bug AND status IN (Done, Closed, Resolved) AND resolved >= -180d AND text ~ "KEYWORDS" ORDER BY resolved DESC
```

```jql
project = NEX AND text ~ "KEYWORDS" ORDER BY updated DESC
```

Use `maxResults: 20` per query. If `pageInfo.hasNextPage` is true, paginate with `nextPageToken: pageInfo.endCursor`.

For additional JQL patterns, see [jql-patterns.md](jql-patterns.md).

### Step 5 — Enrich top matches

For each candidate with meaningful similarity (~60%+ on summary/description), call `getJiraIssue` with `issueIdOrKey` to fetch:
- status, resolution, resolutiondate
- description, components, labels
- issuelinks (Duplicate / Relates / Blocks)
- fixVersions

Deduplicate by issue key across the three queries.

### Step 6 — Classify

| Verdict | Criteria | Recommendation |
|---------|----------|----------------|
| **Duplicate** | Open bug with similar summary/description | Do not open a new ticket — add a comment or link to existing |
| **Regression** | Closed/Done bug with similar symptoms, especially resolved within last 90 days | Open new bug, link to original NEX-XXX, note "Possible regression of NEX-XXX" |
| **New bug** | No meaningful matches | Safe to open a new ticket |
| **Unclear** | Partial matches only | Present top 2–3 candidates and ask the user |

**Regression heuristics:**
- Closed within 90 days + similar description → likely regression
- `Duplicate` or `Relates` link to a closed bug → regression candidate
- Same component/label + same error message → regression candidate

### Step 7 — Optional code enrichment

If the description mentions a service or class name, search the workspace for related `NEX-XXX` TODO comments and recent `git log` on relevant files. Mention findings in the analysis section.

### Step 8 — Report

Use this template (in the user's language):

```markdown
## תוצאת בדיקת Jira / Jira Bug Check Result

**תיאור / Description:** [short summary]
**מסקנה / Verdict:** כפילות | ריגרסיה | באג חדש | לא ברור

### התאמות שנמצאו / Matches found
| Key | Status | Resolved | Similarity |
|-----|--------|----------|------------|
| NEX-123 | Done | 2026-03-01 | High |

### ניתוח / Analysis
Up to 3 short bullet points (one line each). Plain language — no JQL, no code paths.

### המלצה / Recommendation
- Open new ticket / Do not open / Add comment to NEX-XXX
- If regression: reference "Possible regression of NEX-XXX"
```

## MCP tools reference

| Operation | Tool | Notes |
|-----------|------|-------|
| Get cloudId | `getAccessibleAtlassianResources` | Required first |
| JQL search | `searchJiraIssuesUsingJql` | Omit `fields` param |
| Issue details | `getJiraIssue` | Use `issueIdOrKey` |
| Create ticket | `createJiraIssue` | Only when user explicitly asks |

## Do not

- Open Jira tickets automatically unless the user explicitly requests it
- Pass `fields` to `searchJiraIssuesUsingJql`
- Skip MCP and guess ticket numbers
