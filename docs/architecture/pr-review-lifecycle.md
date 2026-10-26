# PR Review Lifecycle

End-to-end path from a GitHub pull-request webhook to a published review.

Interactive diagram (Archify): [Monk PR Review Sequence](diagrams/pr-review-sequence.html)  
Editable source: [diagrams/sources/pr-review-sequence.json](diagrams/sources/pr-review-sequence.json)

## Walkthrough (source-backed)

### 1. Ingress

- **GitHub → Gateway** `POST /webhook/github`
- File: `services/gateway/main.py` → `github_webhook`
- Reads raw body; builds expected `sha256=` HMAC with `GITHUB_WEBHOOK_SECRET`
- Invalid signature → `401 Invalid signature`
- Valid → `POST http://webhook:8001/events` with `Content-Type: application/json`

### 2. Event routing

- **Webhook** `POST /events` (HTTP 202) → `recieve_event` in `services/webhook/main.py`
- `action == "closed"` and `pull_request.merged` → learning path (see [feedback-learning.md](feedback-learning.md))
- Else if `action` not in `opened|reopened|synchronize` → `{status: "skipped"}`
- Else extract `pr_number`, `repository.full_name`, `head.sha`, `installation.id`

### 3. Dedupe + persist

- Lookup `pull_requests` by `(repo_full_name, pr_number, head_sha)`
- Hit → `{status: "already_processing"}` (no enqueue)
- Miss → insert row with `status="pending"`, commit, capture `pr_id`

### 4. Async dispatch

- `analyze_pr.apply_async(..., queue="webhook")`
- Task: `services/webhook/worker.py` → `analyze_pr`
- Worker `POST http://orchestrator:8002/analyze` with JSON:
  - `pr_id`, `pr_number`, `repo_full_name`, `head_sha`, `installation_id`
  - timeout `120` seconds
- No Celery autoretry configuration in code

### 5. Orchestrator analyze

- Endpoint: `POST /analyze` → `services/orchestrator/main.py` → `analyze`
- GitHub App JWT → `POST /app/installations/{id}/access_tokens`
- Fetch diff: `GET /repos/{repo}/pulls/{n}` with `Accept: application/vnd.github.v3.diff`
- Load top-10 `patterns` by frequency for the repo
- `build_graph().invoke({diff, patterns, findings: []})`
- Persist each finding to `findings`
- `POST http://reviewer:8003/post-review` with findings payload

### 6. Review publication

- Endpoint: `POST /post-review` → `services/reviewer/main.py` → `post_review`
- Empty findings → `{status: "ok"}` **without** updating PR status
- Otherwise build summary + inline comments (`side: "RIGHT"`)
- `POST /repos/{repo}/pulls/{n}/reviews` with `event: "COMMENT"`
- On `422` with inline comments → retry summary-only body
- Success → `pull_requests.status = "reviewed"`

## Async boundary

Dashed hops in the sequence diagram are Celery/Redis. The webhook HTTP response returns after enqueue; LLM work runs on the worker → orchestrator path.

## Related

- [System architecture](system-architecture.md)
- [Multi-agent review](multi-agent-review.md)
- [Webhook error handling](webhook-error-handling.md)
