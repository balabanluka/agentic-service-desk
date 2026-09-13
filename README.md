# Agentic Service Desk

A production-oriented reference implementation of a controlled, grounded AI
service desk for **Harborlight Workspace**, a wholly fictional SaaS product. It
uses Python 3.12, FastAPI, LangGraph, OpenAI, Pydantic, PostgreSQL, pgvector,
and pytest.

The project deliberately favors clear control boundaries over simulated
independent agents. One LangGraph orchestrator routes each request into a
single domain workflow. Within that workflow, the model can select useful
read-only business tools from a strict allowlist and receives knowledge retrieved
only from the graph-selected domain.

## What V2 does

- Routes requests to support, billing, technical, or explicit clarification.
- Loads customer-specific facts from original synthetic local business data.
- Retrieves policy and troubleshooting guidance from 18 synthetic Markdown
  documents stored as exactly 20 deterministic chunks.
- Combines business-tool facts and retrieved knowledge into one grounded answer.
- Returns execution metadata: route decision, graph path, tools used, and concise
  knowledge-source identifiers.
- Enforces customer ownership, domain permissions, a three-business-tool-call
  budget, and a bounded three-iteration tool-use loop.
- Provides offline tests, opt-in PostgreSQL integration tests, and versioned
  retrieval/workflow evaluations.

This is not a frontend or a collection of autonomous processes. It performs no
write action and does not ingest knowledge during API startup.

## Architecture and request flow

```text
POST /api/chat
  -> load_customer
  -> route_request (structured route decision)
     -> clarification template, or
     -> support_workflow | billing_workflow | technical_workflow
          -> exact, domain-filtered pgvector retrieval (top 4 by default)
          -> bounded model-selected business-tool loop
          -> final grounded answer inside the selected workflow
```

Answer composition intentionally happens inside each terminal domain workflow.
There is no separate `compose_answer` LangGraph node. If the third permitted
business-tool result is produced, the graph gives the model one final
**answer-only** turn with the accumulated evidence and no business tools. A tool
request during that turn is rejected; it never becomes a fourth call.

The initial customer existence check is part of the graph path and appears in
`tools_used`, but it is not a model-requested workflow call and does not consume
the three-call workflow budget.

### Routing policy

Routing follows the user's primary requested outcome:

| Route | Primary ownership |
|---|---|
| `support` | Password reset, sign-in/account access, invitations, members, roles, and permissions |
| `billing` | Invoices, payments, refunds/credits, billing cycles, and plan/renewal changes |
| `technical` | Exports, API authentication/rate limits, webhooks, incidents, errors, and troubleshooting |

Supporting metadata does not change the primary route. Export troubleshooting
remains technical when it needs subscription or ticket facts; a workspace-role
question remains support even if the role is called Billing Admin. Clarification
is for genuinely independent outcomes or an indeterminate primary intent.
`diagnostic_confidence` is optional diagnostic metadata, not a calibrated
probability and not a routing threshold.

### Scoped business tools

All business tools are read-only and operate on synthetic records.

| Workflow | Model-visible tools |
|---|---|
| Support | `get_customer`, `list_tickets` |
| Billing | `get_customer`, `get_subscription`, `get_invoice` |
| Technical | `get_customer`, `get_subscription`, `list_tickets` |

`get_invoice` verifies that the requested invoice belongs to the current
customer. A cross-customer reference returns a controlled `denied` result and
does not reveal the other customer's invoice.

## V1 and V2

V1 established the FastAPI API, one controlled LangGraph, structured routing,
synthetic business records, domain tool allowlists, and offline tests. The model
could select read-only tools within the selected workflow, but no knowledge
retrieval was available.

V2 adds the frozen Harborlight knowledge corpus, deterministic chunking,
PostgreSQL/pgvector storage, idempotent OpenAI embedding ingestion, exact
domain-scoped retrieval, grounded answer generation, source metadata, bounded
synthesis, and reproducible evaluation. It preserves the V1 API and tool
permission model.

## Knowledge and retrieval design

The 18 source documents live under `knowledge/billing`, `knowledge/support`, and
`knowledge/technical`. Every document has stable front matter with
`document_id`, `title`, `domain`, and `product`.

The structure-aware chunker:

- removes front matter from chunk content;
- preserves Markdown headings, tables, lists, and fenced code blocks;
- treats H2 sections with nested H3 content as semantic units;
- splits oversized units on paragraph boundaries only;
- generates stable IDs such as `KB-TEC-003--chunk-v1--001`;
- records content hashes, source paths, versions, and the frozen source commit.

The frozen corpus produces exactly **20 chunks** (`corpus_version=kb-v1`,
`chunking_version=v1`). Ingestion uses `text-embedding-3-small` with 1536
dimensions by default. A rerun embeds only chunks whose configured-model
fingerprint is absent or whose content hash changed; an unchanged rerun performs
zero embedding calls. Database writes occur only after all required vectors have
been returned and dimension-validated.

Retrieval performs exact pgvector cosine search over active chunks for the
configured corpus and embedding model. The graph supplies the domain filter;
the model cannot choose or broaden it. No HNSW or IVFFlat index is needed for
this 20-chunk corpus. Cosine similarity is a ranking signal, **not confidence**.

## Repository layout

```text
src/service_desk/
  ai/             model protocol and OpenAI Responses API adapter
  api/            FastAPI request, response, health, and error schemas
  data/           synthetic customer/subscription/invoice/ticket repository
  domain/         Pydantic business models
  evaluation/     dataset validation and retrieval/workflow evaluators
  graph/          LangGraph state, orchestration, permissions, bounded loops
  knowledge/      chunking, embeddings, migration, ingestion, and retrieval
  services/       API-safe graph response composition
  tools/          read-only business-tool surface
knowledge/        frozen synthetic Markdown knowledge base
evaluation/
  datasets/       development and immutable held-out cases/manifests
  results/        sanitized, intentionally tracked benchmark summary
tests/            offline unit/API/graph tests and opt-in PostgreSQL tests
```

## Local setup

Use Python 3.12. First create a virtual environment from the repository root:

```bash
python -m venv .venv
```

On macOS or Linux:

```bash
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
```

On Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Set a local database password in `.env` and a real OpenAI API key only for live
ingestion, retrieval, chat, or evaluation. `.env`, `.venv`, `.idea`, caches,
build output, and raw local evaluation reports are ignored.

The principal settings are:

| Variable | Default/purpose |
|---|---|
| `OPENAI_MODEL` | `gpt-5.6-luna` for routing and answer generation |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` |
| `OPENAI_EMBEDDING_DIMENSIONS` | `1536`; must match the current SQL schema |
| `DATABASE_URL` | Local PostgreSQL connection string |
| `KNOWLEDGE_CORPUS_VERSION` | `kb-v1` |
| `KNOWLEDGE_DEFAULT_TOP_K` | `4`, valid range 1–10 |

Never commit the real `.env`.

## Start PostgreSQL and prepare knowledge

Start only the local pgvector database, apply the versioned migration, then run
the explicit ingestion command:

```bash
docker compose up -d postgres
python -m service_desk.knowledge.migrate
python -m service_desk.knowledge.ingest
```

PostgreSQL is bound to `127.0.0.1` and uses the named volume
`agentic_service_desk_postgres_data`. The migration creates the `vector`
extension, `knowledge_chunks`, `knowledge_embeddings`, the migration ledger,
and a B-tree partial index for active corpus/domain filtering.

`knowledge.ingest` calls the OpenAI Embeddings API only for new or changed
chunks. It is never triggered by FastAPI startup. To inspect exact retrieval:

```bash
python -m service_desk.knowledge.search "Why do CSV exports time out for large reports?" --domain technical
```

The search command makes one query-embedding API call.

## Run the API

```bash
uvicorn service_desk.main:app --reload
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Chat request:

```bash
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"customer_id":"cus_orbit_001","message":"Our CSV export keeps timing out. Do we already have a ticket and what should we do?"}'
```

The response shape is:

```json
{
  "answer": "...",
  "execution": {
    "request_id": "...",
    "selected_route": "technical",
    "needs_clarification": false,
    "route_rationale": "...",
    "diagnostic_confidence": 0.98,
    "tools_used": ["get_customer", "list_tickets"],
    "graph_path": ["load_customer", "route_request", "technical_workflow"],
    "answer_source": "model",
    "knowledge_sources": [
      {
        "document_id": "KB-TEC-003",
        "document_title": "CSV export limits and troubleshooting",
        "chunk_id": "KB-TEC-003--chunk-v1--001",
        "source_path": "knowledge/technical/csv-export-limits.md"
      }
    ]
  }
}
```

Unknown customers return 404. Provider, model, or controlled-workflow failures
return a sanitized 503 response. Provider exceptions are logged locally without
API keys, raw vectors, prompts, or provider payloads; bounded-workflow diagnostics
remain available to the evaluation layer without entering the public error body.

Live chat makes an OpenAI routing call, a query-embedding call for the selected
domain, and one or more bounded workflow model calls.

## Tests and validation

The default suite is offline: model, embedding, and repository dependencies are
replaced with deterministic fakes where needed.

```bash
python -m pytest
python -m compileall -q src tests
python -m pip check
python -m service_desk.evaluation.run validate
python -m build --wheel
```

With the Docker database healthy, run the two opt-in PostgreSQL integration
tests explicitly:

```bash
RUN_POSTGRES_TESTS=1 python -m pytest -m postgres
```

On PowerShell, set `$env:RUN_POSTGRES_TESTS='1'` before the pytest command and
remove that environment variable afterward. These integration tests use
deterministic vectors and do not call OpenAI.

The GitHub Actions workflow runs only the offline validation path.

## Evaluation and benchmark integrity

Development cases are separate from immutable held-out versions. Each held-out
JSON file is frozen by a SHA-256 fingerprint in a versioned manifest. Once a
live result has been observed, that version remains historical and is never
edited or presented as a fresh post-fix score.

Validate all manifests and run the graph-contract evaluation offline:

```bash
python -m service_desk.evaluation.run validate
python -m service_desk.evaluation.run workflow-offline --split held_out --workflow-version v3
```

Explicit live modes require `--confirm-live` and incur OpenAI usage. A small
development workflow run is:

```bash
python -m service_desk.evaluation.run workflow-live --split development --limit 1 --confirm-live --output evaluation/reports/workflow-live-development-local.json
```

Live retrieval evaluation also calls OpenAI once per query:

```bash
python -m service_desk.evaluation.run retrieval-live --split development --confirm-live --output evaluation/reports/retrieval-live-development-local.json
```

Raw local reports can contain synthetic answer text and remain ignored under
`evaluation/reports/`. The sanitized history is committed in
`evaluation/results/v2-benchmark-summary.json`.

### Recorded V2 results

The frozen retrieval held-out v1 set contains six cases, two per domain. With
`top_k=4`, its first recorded run produced Hit@1 = 1.0, Hit@4 = 1.0, and
MRR = 1.0, with no failures.

| Workflow set | Historical status | Result | Why another version followed |
|---|---|---|---|
| held-out v1 | Partial initial run plus preserved resume/retry | 4 of 6 unique case outcomes passed | Exposed a bounded-loop synthesis defect; one mixed-domain expectation was also questionable |
| held-out v2 | First complete run | 3/6 passed; route accuracy 0.5; safety 1/1 | Exposed missing domain ownership and primary-intent routing rules |
| held-out v3 | First complete post-fix run | 6/6 passed; route, clarification, tool, source, and applicable safety checks all passed | Final V2 validation set; no further product defect found |

Manual review of v3 found that the answers separated customer facts from policy
guidance, stayed cautious when records could not prove a duplicate charge, kept
the cross-workspace invoice private, and gave actionable support and technical
steps grounded in the expected documents.

These are small, synthetic scenario sets. A 1.0 metric on them does **not** mean
the system has general 100% accuracy, calibrated confidence, or production-scale
coverage.

## Known V2 boundaries

- Business records and knowledge are synthetic and local.
- Retrieval is dense-vector-only; there is no hybrid keyword search or reranker.
- The API has no real authentication layer; `customer_id` is supplied directly
  for demonstration, while ownership is enforced inside scoped tools.
- Retrieval failure is non-fatal: the workflow may answer from business facts
  while stating that general guidance cannot be confirmed.
- Model behavior remains probabilistic, so production deployments need broader
  evaluation, monitoring, rate-limit handling, and authenticated identity.

## Roadmap after V2

V3 may add MCP integrations, authenticated external systems, explicit human
approval for sensitive or write actions, Langfuse-style observability, and a
frontend. None of those capabilities are part of V2.
