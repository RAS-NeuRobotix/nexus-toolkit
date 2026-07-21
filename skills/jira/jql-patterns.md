# JQL Patterns for NEX Project

Base URL: `https://dominionx.atlassian.net`
Project key: `NEX`

## Text search

Jira `text ~` searches summary, description, and comments:

```jql
project = NEX AND text ~ "map timeout safety-critical"
```

Use quoted phrases for multi-word terms. Combine 2–4 distinctive terms rather than the full description.

## Open bugs (duplicate check)

```jql
project = NEX AND issuetype = Bug AND status NOT IN (Done, Closed, Resolved) AND text ~ "KEYWORDS" ORDER BY updated DESC
```

## Recently resolved bugs (regression check)

```jql
project = NEX AND issuetype = Bug AND status IN (Done, Closed, Resolved) AND resolved >= -180d AND text ~ "KEYWORDS" ORDER BY resolved DESC
```

Narrow to last 90 days for high-confidence regression candidates:

```jql
project = NEX AND issuetype = Bug AND status = Done AND resolved >= -90d AND text ~ "KEYWORDS" ORDER BY resolved DESC
```

## All issue types

Use when the bug might be tracked as Story/Task rather than Bug:

```jql
project = NEX AND text ~ "KEYWORDS" ORDER BY updated DESC
```

## By component or label

When the user names a specific area:

```jql
project = NEX AND component = "safety-critical-manager" AND text ~ "KEYWORDS" ORDER BY updated DESC
```

```jql
project = NEX AND labels = regression AND text ~ "KEYWORDS" ORDER BY updated DESC
```

## By service keywords (common NEX areas)

| Area | Example JQL fragment |
|------|---------------------|
| Safety critical | `text ~ "safety-critical-manager OR NexusCoreMapDtmClient"` |
| Nexus core | `text ~ "nexus-core OR nexus core"` |
| GIS / maps | `text ~ "map DTM geographic"` |
| Starlite | `text ~ "starlite OR NEX-27"` |

## Pagination

`searchJiraIssuesUsingJql` returns `pageInfo.hasNextPage` and `pageInfo.endCursor`. Pass `endCursor` as `nextPageToken` on the next request. Use `maxResults: 20` for initial queries.

## MCP call example

```
searchJiraIssuesUsingJql(
  cloudId: "<from getAccessibleAtlassianResources>",
  jql: "project = NEX AND issuetype = Bug AND status NOT IN (Done, Closed, Resolved) AND text ~ \"map timeout\" ORDER BY updated DESC",
  maxResults: 20
)
```

Do **not** pass `fields` — it serializes incorrectly in this runtime.
