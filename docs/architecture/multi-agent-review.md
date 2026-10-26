# Multi-Agent Review

How the orchestrator runs four specialized reviewers in parallel via LangGraph, then merges and publishes findings.

Interactive diagram (Archify): [Monk Multi-Agent LangGraph Review](diagrams/multi-agent-review.html)  
Editable source: [diagrams/sources/multi-agent-review.json](diagrams/sources/multi-agent-review.json)

## Graph shape

Defined in `services/orchestrator/graph.py` → `build_graph()`:

1. **Conditional entry** `fan_out` returns four `Send(...)` objects (parallel).
2. Nodes: `static_analysis`, `security`, `style`, `architecture`.
3. Every agent edge leads to `merge`, then `END`.

State (`GraphState`):

- `diff: str`
- `patterns: list` (loaded as pattern text strings; style prompt joins them)
- `findings: Annotated[list, operator.add]` so parallel writes concatenate

## Agents

| Node | Prompt source | Notes |
| --- | --- | --- |
| `static_analysis` | `PROMPTS["static_analysis"]` | Complexity, dead code, naming, maintainability |
| `security` | `PROMPTS["security"]` | Injection, authz, secrets, XSS/SSRF, etc. |
| `style` | `_style_prompt(state)` | Injects learned patterns into the system prompt |
| `architecture` | `PROMPTS["architecture"]` | Boundaries, reliability, consistency |

Each agent calls Gemini through Langfuse’s OpenAI-compatible client:

- Model: `gemini-3.8-flash`
- User message: the PR diff
- Output: JSON array of `{file, line, severity, message}`; agent name is attached in code

## Merge + validation

- `parse_json_response`: strips optional ` ```json ` fences; on `JSONDecodeError` returns `[]` (soft fail per agent).
- `merge_node`: dedupes on `(file, line, agent, message)`.
- There is **no** structural schema validation of severity enums or required keys beyond JSON parse.

## Persistence and publish

After `invoke`, `services/orchestrator/main.py`:

1. Inserts findings rows (`Finding` model)
2. Calls Reviewer `POST /post-review` with the merged list

## Parallelism note

Independent agents are **not** sequenced. Fan-out uses LangGraph `Send`; implying a serial agent pipeline would be incorrect.

## Related

- [PR review lifecycle](pr-review-lifecycle.md)
- [Feedback learning](feedback-learning.md) (pattern injection into style only)
