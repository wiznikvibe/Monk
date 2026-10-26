# Feedback-Learning Lifecycle

How merged PRs update repo-specific patterns used by later style reviews.

Interactive diagram (Archify): [Monk Feedback-Learning Lifecycle](diagrams/feedback-learning.html)  
Editable source: [diagrams/sources/feedback-learning.json](diagrams/sources/feedback-learning.json)

## Trigger

In `services/webhook/main.py` → `recieve_event`:

- When `action == "closed"` and `pull_request.merged` is true
- Lookup `pull_requests` by `(pr_number, repo_full_name)` (**not** by `head_sha`)
- If a row exists: `trigger_learning.apply_async([repo_full_name, pr_id], queue="learning")`
- Always returns `{status: "accepted"}` for this branch (even if no row / no enqueue)

## Task and HTTP call

`trigger_learning` is defined in **`services/webhook/worker.py`** (not in the learner service module):

```text
POST http://learner:8004/learn
{"repo_full_name": "...", "pr_id": "..."}
```

Kubernetes `learner-worker` runs `celery -A worker -Q learning` on the **learner** image (`infra/k8s/learner-worker.yaml`), while `services/learner/worker.py` only configures the Celery app and task route—it does **not** register `trigger_learning`. Whether learning executes in a given cluster depends on which image/process actually consumes `Q:learning`. Treat this as a deployment risk documented from source, not as a proven production success path.

## Learner API

`POST /learn` → `services/learner/main.py` → `learn`:

1. Select findings for `pr_id` with `severity in ('warning', 'error')`
2. For each finding, upsert into `patterns`:
   - `pattern_text = finding.message`
   - unique `(repo_full_name, pattern_text)`
   - on conflict: `frequency = frequency + 1`
3. Return `{status: "ok"}`

Info-severity findings are ignored.

## Consumption on later reviews

`services/orchestrator/main.py` loads:

```text
SELECT patterns WHERE repo_full_name = ? ORDER BY frequency DESC LIMIT 10
```

Only the **style** agent prompt includes those strings (`_style_prompt` in `graph.py`). Other agents do not receive learned patterns.

## Related

- [Multi-agent review](multi-agent-review.md)
- [System architecture](system-architecture.md)
