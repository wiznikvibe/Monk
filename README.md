# Monk

**Monk** is a multi-agent, AI-powered GitHub code review platform. A GitHub App installation delivers pull-request webhooks; Monk verifies them at the edge, analyzes each diff with specialized LLM agents in parallel, posts structured review comments, and can promote recurring findings into repo-specific patterns for later style reviews.

It is built as distributed FastAPI services with Celery workers, PostgreSQL, Redis, LangGraph orchestration, and Kubernetes/Terraform scaffolding. Treat this repository as an **engineering system under active development**—production-oriented pieces exist, but readiness depends on correct secrets, cluster wiring, and the known gaps called out below.

---

## Problem and motivation

Manual review does not scale with PR volume. Linters catch syntax and local style; they rarely reason about security paths, architectural coupling, or team-specific smells that only show up after several merges.

Monk sits in the middle of that gap:

- **Event-driven** — reacts to GitHub PR webhooks (`opened`, `reopened`, `synchronize`, and `closed` when merged)
- **Multi-agent** — static analysis, security, style, and architecture agents run via LangGraph fan-out
- **Feedback-aware** — merged-PR findings can upsert into a per-repo pattern store used by later style prompts
- **Separable scaling** — thin public gateway, async workers, and independently deployable services

---

## Key features (implemented in source)

- GitHub webhook HMAC-SHA256 verification at the gateway
- PR dedupe on `(repo_full_name, pr_number, head_sha)` before enqueue
- Celery tasks `analyze_pr` (`webhook` queue) and `trigger_learning` (`learning` queue)
- GitHub App JWT → installation token → PR diff fetch
- LangGraph parallel agents + merge dedupe
- Reviewer posts `COMMENT` reviews with inline comments and a 422 summary-only fallback
- Learner upserts `warning`/`error` finding messages into `patterns`
- Prometheus instrumentation on FastAPI apps; scrape config under `monitoring/`
- Per-service GitHub Actions CI (test → ECR → EKS image roll on `main`)
- Unit tests under each `services/*/tests/`

---

## Architecture overview

Interactive Archify diagram: **[System architecture](docs/architecture/diagrams/system-architecture.html)**  
Deep dive: [docs/architecture/system-architecture.md](docs/architecture/system-architecture.md)

```
GitHub → ALB → Gateway (:8000) → Webhook (:8001) → Redis/Celery
                                      ↓
                              Webhook worker → Orchestrator (:8002)
                                      ↓              ↘ Gemini
                                 Reviewer (:8003) → GitHub Reviews API
                                      ↓
                                 PostgreSQL ← Learner (:8004) ← learning queue
```

**Why this shape**

- Webhook intake stays cheap and synchronous; LLM work is asynchronous.
- Gateway is the trust boundary (signature check only).
- Orchestrator owns GitHub read + graph execution; Reviewer owns GitHub write.

---

## End-to-end PR lifecycle

Interactive Archify sequence: **[PR review sequence](docs/architecture/diagrams/pr-review-sequence.html)**  
Narrative: [docs/architecture/pr-review-lifecycle.md](docs/architecture/pr-review-lifecycle.md)

1. GitHub sends `POST /webhook/github` with `X-Hub-Signature-256`.
2. Gateway verifies HMAC; on success forwards to `POST /events` on the webhook service.
3. Eligible PR actions persist a `pull_requests` row and enqueue `analyze_pr`.
4. Worker calls `POST /analyze` on the orchestrator (timeout 120s).
5. Orchestrator fetches the diff, loads patterns, runs LangGraph, stores findings.
6. Orchestrator calls `POST /post-review`; Reviewer comments on the PR and sets `status=reviewed`.

Merged PRs take the learning path documented in [feedback-learning.md](docs/architecture/feedback-learning.md).

---

## Multi-agent architecture

Interactive Archify diagram: **[Multi-agent review](docs/architecture/diagrams/multi-agent-review.html)**  
Narrative: [docs/architecture/multi-agent-review.md](docs/architecture/multi-agent-review.md)

LangGraph entry `fan_out` issues four parallel `Send`s:

| Agent | Focus |
| --- | --- |
| `static_analysis` | Complexity, dead code, naming, maintainability |
| `security` | Injection, authn/z, secrets, web/security misconfig |
| `style` | Formatting/consistency **plus** learned pattern text |
| `architecture` | Boundaries, reliability, consistency, coupling |

Results merge with dedupe key `(file, line, agent, message)`. Invalid agent JSON becomes `[]` for that agent.

---

## Technology stack

| Layer | Choices |
| --- | --- |
| Runtime | Python 3.11, FastAPI, Uvicorn |
| AI | LangGraph, Langfuse OpenAI client → Google Gemini (`gemini-3.8-flash`) |
| Jobs | Celery, Redis broker |
| Data | PostgreSQL (SQLAlchemy async + asyncpg), Alembic |
| GitHub | App JWT → installation tokens; webhook HMAC |
| Observability | Prometheus FastAPI instrumentator; Grafana dashboard JSON; Langfuse settings on orchestrator |
| Evaluation | Offline `scripts/evaluate.py` (Ragas)—see known limitations |
| Infra | Terraform under `infra/terraform/`; manifests under `infra/k8s/` |
| CI/CD | GitHub Actions → ECR → `kubectl set image` |

---

## Repository structure

```
monk/
├── services/
│   ├── gateway/         # Public webhook edge (HMAC → forward)
│   ├── webhook/         # /events, PR persistence, Celery tasks
│   ├── orchestrator/    # /analyze + LangGraph agents
│   ├── reviewer/        # /post-review → GitHub
│   └── learner/         # /learn pattern upsert
├── db/migrations/       # Alembic (pull_requests, findings, patterns)
├── scripts/             # Offline evaluation job
├── infra/terraform/     # AWS networking / EKS-oriented modules
├── infra/k8s/           # Deployments, workers, Ingress, HPA, Jobs
├── monitoring/          # Prometheus scrape + Grafana dashboard
├── docs/architecture/   # Architecture notes + Archify diagrams
└── .github/workflows/   # Per-service CI/CD + reusable pipeline
```

---

## Services and APIs

| Service | Port | Endpoints | Notes |
| --- | --- | --- | --- |
| Gateway | 8000 | `GET /health`, `POST /webhook/github` | Forwards to `http://webhook:8001/events` |
| Webhook | 8001 | `GET /health`, `POST /events` | Enqueues Celery; 202 on accept |
| Orchestrator | 8002 | `GET /health`, `POST /analyze` | Sync graph invoke inside request |
| Reviewer | 8003 | `GET /health`, `POST /post-review` | GitHub Reviews API writer |
| Learner | 8004 | `GET /health`, `POST /learn` | Pattern upsert |

Celery (from `services/webhook/worker.py`):

- `analyze_pr` → queue `webhook`
- `trigger_learning` → queue `learning`

---

## Data model

From `db/migrations/versions/0001_initial.py`:

| Table | Purpose |
| --- | --- |
| `pull_requests` | Work items: repo, number, head SHA, installation id, status |
| `findings` | Per-agent findings tied to a PR |
| `patterns` | Repo-scoped recurring issue text + frequency (unique on repo + text) |

Status values observed in code: `pending` at insert; `reviewed` after a successful non-empty review post.

---

## Security considerations

- Webhook authenticity: HMAC-SHA256 over the **raw** body (`hmac.compare_digest`)
- GitHub App private key and webhook secret are expected via environment / cluster Secret (local `infra/k8s/secret.yaml` and `configmap.yaml` are **gitignored**—do not commit real credentials)
- Reviewer never echoes secret values from findings by policy in prompts; still treat model output as untrusted before acting on it elsewhere
- Only the gateway is exposed via the ALB Ingress in-tree; other services use cluster DNS names

---

## Error handling and reliability

Interactive Archify workflow: **[Webhook error handling](docs/architecture/diagrams/webhook-error-handling.html)**  
Details: [docs/architecture/webhook-error-handling.md](docs/architecture/webhook-error-handling.md)

**Present:** signature rejection, action skip, SHA dedupe, JSON soft-fail per agent, GitHub 422 summary fallback.

**Absent in code:** Celery autoretry/backoff, explicit PR `failed` status, dead-letter handling.

---

## Observability and evaluation

- Each FastAPI app exposes Prometheus metrics via `Instrumentator().instrument(app).expose(app)`
- `monitoring/prometheus.yml` scrapes gateway/webhook/orchestrator/reviewer/learner `/metrics`
- Orchestrator Settings include Langfuse host/key fields; graph client imports `langfuse.openai.OpenAI`
- `scripts/evaluate.py` runs an offline Ragas-style job—**unverified as correct**: the SQL selects `f.findings` (column does not match the `findings` schema’s `message` field) and imports `faithfullness` (spelling). Treat evaluation as experimental until fixed.

---

## Local development and setup

There is no root `docker-compose` in this repository. Practical local loop:

```bash
# Python 3.11 recommended
cd services/gateway && pip install -r requirements.txt
# repeat per service under services/{gateway,webhook,orchestrator,reviewer,learner}

# Unit tests (from each service directory)
pytest

# Or from repo root, example:
python -m pytest services/gateway/tests services/webhook/tests \
  services/orchestrator/tests services/reviewer/tests services/learner/tests
```

Cluster-shaped run expects Kubernetes DNS (`webhook`, `orchestrator`, `reviewer`, `learner`, Redis, Postgres) as hardcoded in workers/gateway forward URL. Point those names via local overrides only if you change code (not done in this docs pass).

Database migrations:

```bash
# from an environment with DATABASE_URL and Alembic configured under db/
alembic upgrade head
```

(Exact `alembic.ini` working directory follows `db/migrations` layout.)

---

## Configuration and environment variables

Names inferred from Settings / `os.getenv` (values belong in secrets managers—**never commit real secrets**):

| Variable | Used by | Purpose |
| --- | --- | --- |
| `GITHUB_WEBHOOK_SECRET` | Gateway | HMAC verification |
| `DATABASE_URL` / `database_url` | Webhook, Orchestrator, Reviewer, Learner | Postgres async URL |
| `REDIS_URL` | Webhook/Learner workers | Celery broker |
| `GITHUB_APP_ID` | Orchestrator, Reviewer | App JWT `iss` |
| `GITHUB_APP_PRIVATE_KEY` | Orchestrator, Reviewer | RS256 private key (`\n` escaped OK) |
| `GOOGLE_API_KEY` | Orchestrator graph | Gemini client |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST` | Orchestrator settings | Tracing config surface |
| `openai_api_key` (Settings field) | Orchestrator models | Declared; graph uses `GOOGLE_API_KEY` |

Pydantic Settings read `.env` when present. Cluster ConfigMap keys such as `WEBHOOK_SERVICE_URL` are **not referenced** by the Python services (URLs are hardcoded).

---

## Testing

Per-service pytest suites live under `services/*/tests/`. CI runs `pytest` when a `tests` directory exists (`/.github/workflows/service-ci.yml`).

---

## Deployment architecture

- Terraform modules under `infra/terraform/` provision AWS-oriented resources (see `main.tf` / variables).
- `infra/k8s/` includes Deployments for each API, `webhook-worker`, `learner-worker`, Ingress, HPA (orchestrator 2–6 @ 70% CPU), migration and evaluate Jobs.
- Ingress exposes **gateway** only on port 8000.

---

## CI/CD

Reusable workflow `.github/workflows/service-ci.yml`:

1. Install service requirements; run pytest if tests exist
2. On push to `main`: build/push ECR image tagged with `GITHUB_SHA` and `latest`
3. `kubectl set image` for the matching Deployment

Service-specific workflows call that reusable pipeline.

---

## Known limitations and future improvements

Documented from source review (not speculative roadmap marketing):

1. **Learning worker registration gap** — `trigger_learning` is registered in `services/webhook/worker.py`; `services/learner/worker.py` does not define the task, while `learner-worker` runs the learner image. Validate which consumer actually drains `Q:learning` before relying on learning in a cluster.
2. **Hardcoded service URLs** — gateway/workers ignore ConfigMap service URL keys.
3. **Empty findings** leave PR status at `pending`.
4. **No Celery retries** on analysis/learning tasks.
5. **Evaluation script** SQL/metric naming looks inconsistent with the schema; do not treat Ragas gate as authoritative until repaired.
6. **Merged learning lookup** uses `(repo, pr_number)` only—multiple SHA rows for one PR may resolve to an arbitrary match depending on DB ordering (`scalar_one_or_none` without `ORDER BY`).
7. Archify system diagram automated gates passed; perceptual route-crossing review was recommended by the tool and is not claimed here.

---

## Architecture documentation index

| Doc | Diagram |
| --- | --- |
| [System architecture](docs/architecture/system-architecture.md) | [HTML](docs/architecture/diagrams/system-architecture.html) |
| [PR review lifecycle](docs/architecture/pr-review-lifecycle.md) | [HTML](docs/architecture/diagrams/pr-review-sequence.html) |
| [Multi-agent review](docs/architecture/multi-agent-review.md) | [HTML](docs/architecture/diagrams/multi-agent-review.html) |
| [Webhook error handling](docs/architecture/webhook-error-handling.md) | [HTML](docs/architecture/diagrams/webhook-error-handling.html) |
| [Feedback learning](docs/architecture/feedback-learning.md) | [HTML](docs/architecture/diagrams/feedback-learning.html) |
| [LinkedIn showcase draft](docs/linkedin-post.md) | — |

Editable Archify JSON: `docs/architecture/diagrams/sources/`.

Open the HTML files locally in a browser (GitHub’s markdown preview does not execute embedded Archify viewers).

---

## License

Proprietary / private — update this section if the project is open-sourced.
