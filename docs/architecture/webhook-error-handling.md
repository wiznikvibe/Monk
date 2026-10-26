# Webhook Error Handling and Recovery

Failure and recovery paths that exist in the current code—and gaps that do not.

Interactive diagram (Archify): [Monk Webhook Error Handling](diagrams/webhook-error-handling.html)  
Editable source: [diagrams/sources/webhook-error-handling.json](diagrams/sources/webhook-error-handling.json)

## Implemented recovery

| Condition | Behavior | Source |
| --- | --- | --- |
| Invalid `X-Hub-Signature-256` | HTTP `401` at Gateway; webhook never called | `services/gateway/main.py` |
| Unsupported `action` | `{status: "skipped"}` | `services/webhook/main.py` |
| Duplicate `(repo, pr, head_sha)` | `{status: "already_processing"}`; no second enqueue | `services/webhook/main.py` |
| Agent returns non-JSON | That agent contributes `[]` | `parse_json_response` in `graph.py` |
| GitHub review `422` with inline comments | Retry summary-only review | `services/reviewer/main.py` |

## Soft / silent paths

| Condition | Behavior | Implication |
| --- | --- | --- |
| Empty findings list | Reviewer returns `ok` immediately | PR `status` stays `pending` |
| Merged event with no prior PR row | Learning not enqueued; still `{status: "accepted"}` | Silent no-op |
| Upstream webhook HTTP error after valid HMAC | Gateway `raise_for_status()` | GitHub may retry delivery |

## Missing recovery (verified absent)

- No Celery `autoretry_for` / backoff on `analyze_pr` or `trigger_learning`
- Orchestrator GitHub/LLM failures propagate via `raise_for_status` / uncaught exceptions
- No dead-letter queue or compensating “failed” PR status transition in application code
- No idempotent “review already posted” guard beyond SHA dedupe at intake

## Related

- [PR review lifecycle](pr-review-lifecycle.md)
- [System architecture](system-architecture.md)
