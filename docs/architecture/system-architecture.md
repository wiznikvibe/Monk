# System Architecture

Monk is a multi-service GitHub App that turns pull-request webhooks into parallel LLM reviews and optional repo-specific learning.

Interactive diagram (Archify): [Monk System Architecture](diagrams/system-architecture.html)  
Editable source: [diagrams/sources/system-architecture.json](diagrams/sources/system-architecture.json)

Pinned evidence revision: `6fff47a81276d0e1cc00d3ca0c7041aaba008c0a` (`https://github.com/wiznikvibe/Monk.git`).

## Responsibilities

| Component | Port / queue | Role |
| --- | --- | --- |
| ALB Ingress | `:80` → gateway | Public entry (`infra/k8s/ingress.yaml`) |
| Gateway | `:8000` | HMAC verify; forward raw body |
| Webhook API | `:8001` | Route PR actions; persist; enqueue |
| Redis / Celery | broker | Queues `webhook` and `learning` |
| Webhook worker | `Q:webhook` | `analyze_pr` → Orchestrator |
| Orchestrator | `:8002` | Diff fetch, LangGraph, persist findings |
| Reviewer | `:8003` | GitHub PR review + status update |
| Learner worker | `Q:learning` | Intended consumer of `trigger_learning` |
| Learner API | `:8004` | Upsert patterns from findings |
| PostgreSQL | — | `pull_requests`, `findings`, `patterns` |
| Gemini | external | Agent LLM (`gemini-3.8-flash`) |

## Main request path

1. GitHub delivers a webhook to the ALB → Gateway `POST /webhook/github`.
2. Gateway verifies `X-Hub-Signature-256` (`services/gateway/main.py`).
3. Gateway `POST`s the raw body to `http://webhook:8001/events`.
4. Webhook inserts a `pull_requests` row (when eligible) and enqueues Celery.
5. Worker calls Orchestrator `POST /analyze`; Orchestrator calls Reviewer `POST /post-review`.
6. Reviewer posts to GitHub Reviews API and sets `status=reviewed`.

Learning and observability are side paths; see [feedback-learning.md](feedback-learning.md) and the observability notes in the README.

## Engineering decisions (as implemented)

- **Thin edge**: Gateway contains no PR business logic—only signature verification and forward.
- **Async analysis**: Webhook returns after enqueue so GitHub delivery is not blocked by LLM latency.
- **Hardcoded cluster DNS**: Workers call `http://orchestrator:8002` / `http://learner:8004` directly; ConfigMap `*_SERVICE_URL` values are not read by application code (ConfigMap is gitignored and not part of HEAD evidence).

## Related

- [PR review lifecycle](pr-review-lifecycle.md)
- [Multi-agent review](multi-agent-review.md)
- [Webhook error handling](webhook-error-handling.md)
- [Feedback learning](feedback-learning.md)
