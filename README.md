# Agentic Service Desk

A production-oriented reference implementation of a controlled AI service desk for
**Harborlight Workspace**, a wholly fictional SaaS product. It uses Python 3.12,
FastAPI, LangGraph, OpenAI, Pydantic, PostgreSQL/pgvector, the official MCP Python
SDK, and pytest.

The project uses one explicit orchestrator—not simulated independent agents. The
model can select only tools exposed by the graph-selected domain. Reads run
automatically; ticket writes become durable proposals and cannot execute until a
separate human approval request reaches the API.

## Releases

- **V1 — controlled agent foundation:** FastAPI, one LangGraph, structured routing,
  synthetic business data, scoped read tools, and bounded model tool use.
- **V2 — grounded RAG and evaluation:** 18 frozen knowledge documents, 20 stable
  chunks, pgvector ingestion/retrieval, grounded answers, and immutable benchmarks.
- **V3 — MCP actions and human approval:** mutable PostgreSQL tickets, real
  Streamable HTTP MCP, explicit write-intent gating, durable actions, idempotent
  approval, exactly-once mutation receipts, and an append-only audit trail.

V3 does not add a frontend, production authentication, payment mutations, Langfuse,
or other V4 features.

## V3 architecture

```text
POST /api/chat
  -> load_customer (synthetic read-only customer index)
  -> route_request (route + clarification + detected write_intents)
     -> clarification template; no domain/action tools, or
     -> support | billing | technical workflow
          -> exact pgvector retrieval fixed to that domain
          -> model-selected tools from that workflow's allowlist
             -> customer/subscription/invoice reads
             -> ticket reads through MCP
             -> ticket write proposal only when router detected explicit intent
          -> grounded answer inside the selected workflow

write proposal
  -> PostgreSQL ticket_actions(status=pending)
  -> GET /api/actions/{id} for review
  -> POST .../approve or .../reject
     -> reject: terminal, no MCP write
     -> approve: MCP Streamable HTTP call carrying action_id only
          -> MCP reloads approved canonical action
          -> ticket mutation + unique receipt in one DB transaction
          -> durable succeeded/failed/executing state + audit events
```

Answer composition remains inside each terminal domain workflow; there is no
separate `compose_answer` graph node. The normal model loop permits at most three
model-requested tool calls across three tool-use iterations. After the final allowed
tool result, one tools-empty synthesis turn may compose an answer. It cannot execute
a fourth read, proposal, or write.

### Why approval is not a LangGraph interrupt

LangGraph interrupts are useful when the same long-running graph execution must be
resumed. Here, chat proposes a durable resource and a later HTTP request may approve
it after a process restart. A small PostgreSQL action state machine makes that API
lifecycle, concurrency behavior, audit history, and MCP idempotency explicit. The
LangGraph still controls routing and proposal permissions; approved execution is a
separate application service. This avoids replaying a model node merely to carry out
an already-reviewed mutation.

## Routing and tool permissions

Routing follows the primary requested outcome. Supporting metadata never changes the
primary domain.

| Route | Primary ownership | Automatic V2 reads |
|---|---|---|
| `support` | Sign-in/access, invitations, members, roles, permissions | `get_customer`, `list_tickets` |
| `billing` | Invoices, payments, refunds/credits, billing cycles, plan/renewal changes | `get_customer`, `get_subscription`, `get_invoice` |
| `technical` | Exports, APIs, webhooks, incidents, errors, troubleshooting | `get_customer`, `get_subscription`, `list_tickets` |

Ticket reads use MCP in the configured V3 application. Other synthetic account reads
retain their V2 local implementations. Invoice and ticket lookups enforce the current
`customer_id`; another customer's object is returned only as a generic denied/not
available result.

The router also returns `write_intents`, chosen from `create_ticket`,
`update_ticket_status`, and `update_ticket_priority`. This is detected intent, not
authorization. The selected workflow receives only the matching proposal tool. A
hypothetical or informational question receives no proposal tools. A clarification
decision enters no workflow even if it reports one detected intent.

| Model-visible proposal tool | Durable effect | Business mutation |
|---|---|---|
| `propose_create_ticket` | inserts a pending canonical action | none |
| `propose_update_ticket_status` | inserts a pending canonical action after scoped ticket validation | none |
| `propose_update_ticket_priority` | inserts a pending canonical action after scoped ticket validation | none |

The MCP server separately exposes `tickets_list`, `ticket_get`, `ticket_create`,
`ticket_update_status`, and `ticket_update_priority`. Every MCP tool publishes
deterministic effect metadata. Reads have `readOnlyHint=true`; writes have
`readOnlyHint=false`, `idempotentHint=true`, and
`service_desk.approval_required=true`. These annotations aid inspection, but the MCP
server also enforces approval from durable database state.

## Approval, exactly-once execution, and audit

Action states are:

```text
pending -> rejected
pending -> expired
pending -> executing -> succeeded
                     -> failed (definitive rejection)
                     -> executing (ambiguous transport failure; retry safely)
```

The pending record contains the customer, route, typed canonical payload, expiry,
proposal request identity, and an approval-required flag. The model never receives
the MCP execution tools and cannot mark an action approved.

Approval is safe under duplicate and concurrent requests:

1. The application row-locks the action and atomically records durable `approved`
   and `execution_started` audit events while moving it to `executing`.
2. It calls the MCP client with only the `action_id` and expected action type.
3. The MCP server row-locks the canonical action, verifies its state/type, and
   performs the customer-and-domain-scoped mutation.
4. The mutation and unique `ticket_action_receipts.action_id` are committed in one
   PostgreSQL transaction.
5. Every retry returns the stored receipt. A completed action returns its existing
   terminal result.

If the network times out after the server may have committed, the action stays
`executing`; retrying approval reconciles through the same receipt. A definitive MCP
tool rejection becomes `failed`. There is never a local-write fallback. Rejection or
expiry never calls a write tool.

`ticket_action_audit_events` is append-only and records sanitized lifecycle facts.
It does not store API keys, hidden prompts, provider payloads, or vectors.

## Knowledge and grounded answers

The V2 knowledge base remains frozen under `knowledge/billing`, `knowledge/support`,
and `knowledge/technical`. Its parser removes front matter, preserves Markdown
structures, and deterministically produces exactly **20 chunks** with IDs such as
`KB-TEC-003--chunk-v1--001` (`corpus_version=kb-v1`, `chunking_version=v1`).

Ingestion uses configurable `text-embedding-3-small` 1536-dimensional embeddings.
An unchanged run makes zero embedding calls. Retrieval uses exact pgvector cosine
ranking over active chunks, filters by the graph-selected domain and embedding model,
and defaults to top 4. Cosine similarity is a ranking signal, not confidence.

Answers may combine customer-specific tool facts, pending-action facts, and retrieved
general guidance. They must state what cannot be confirmed and distinguish a pending
proposal from an executed action. The API returns concise KB source metadata, never
raw vectors or full retrieved chunks.

## Repository layout

```text
src/service_desk/
  ai/             structured router/workflow model gateway
  api/            FastAPI chat, action, health, and error contracts
  data/           immutable synthetic customer/account bootstrap data
  domain/         Pydantic business entities
  evaluation/     V2 retrieval/workflow and V3 action evaluators
  graph/          LangGraph state, routing, scoped tools, bounded synthesis
  knowledge/      chunking, migrations, ingestion, retrieval
  ticketing/      action service, psycopg repositories, MCP server/client, seeding
  services/       API-safe response composition
knowledge/        18 frozen synthetic Markdown documents
evaluation/
  datasets/       development and immutable versioned held-out data
  reports/        intentionally tracked held-out first reports; other reports ignored
  results/        compact benchmark histories
tests/            offline tests and opt-in PostgreSQL/MCP integration tests
```

## Local setup

Use Python 3.12. From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate                 # macOS/Linux
python -m pip install -e ".[dev]"
cp .env.example .env
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Set a local database password and OpenAI key only in `.env`. Never commit it.

| Setting | Default/purpose |
|---|---|
| `OPENAI_MODEL` | `gpt-5.6-luna` |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` |
| `OPENAI_EMBEDDING_DIMENSIONS` | `1536` |
| `DATABASE_URL` | localhost PostgreSQL connection |
| `KNOWLEDGE_CORPUS_VERSION` | `kb-v1` |
| `KNOWLEDGE_DEFAULT_TOP_K` | `4` (valid 1–10) |
| `MCP_TICKET_SERVER_URL` | `http://127.0.0.1:8001/mcp` |
| `MCP_REQUEST_TIMEOUT_SECONDS` | `10` |
| `ACTION_TTL_MINUTES` | `30` |

### Database, knowledge, and ticket bootstrap

```bash
docker compose up -d postgres
python -m service_desk.knowledge.migrate
python -m service_desk.ticketing.seed
python -m service_desk.knowledge.ingest
```

The checksummed migration runner applies both V2 and V3 migrations. Existing V2
databases receive only `002_ticket_actions.sql`; a clean database applies both.
Ticket seeding is explicit and idempotent. The tracked JSON is bootstrap data, not
runtime mutable storage. Knowledge ingestion is never triggered at API startup.

`knowledge.ingest` calls OpenAI only for new/changed chunks. Exact search makes one
query-embedding call:

```bash
python -m service_desk.knowledge.search "Why do CSV exports time out?" --domain technical
```

### Run MCP and FastAPI

Start these in separate terminals after PostgreSQL is healthy:

```bash
python -m service_desk.ticketing.mcp_server
uvicorn service_desk.main:app --reload --port 8000
```

MCP binds only to `127.0.0.1:8001` and serves Streamable HTTP at `/mcp`. FastAPI does
not bypass it when ticket operations fail.

## API examples

```bash
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"customer_id":"cus_orbit_001","message":"Our CSV export times out. Do we already have a ticket?"}'
```

Propose a write (this does **not** create the ticket):

```bash
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"customer_id":"cus_orbit_001","message":"Create a high-priority technical ticket for the recurring CSV timeout."}'
```

The response execution metadata includes:

```json
{
  "selected_route": "technical",
  "write_intents": ["create_ticket"],
  "pending_actions": [{
    "action_id": "act_...",
    "action_type": "create_ticket",
    "status": "pending",
    "approval_required": true,
    "expires_at": "..."
  }]
}
```

Review, approve, or reject with the same customer ownership guard:

```bash
curl "http://127.0.0.1:8000/api/actions/act_...?customer_id=cus_orbit_001"
curl -X POST http://127.0.0.1:8000/api/actions/act_.../approve \
  -H "Content-Type: application/json" -d '{"customer_id":"cus_orbit_001"}'
curl -X POST http://127.0.0.1:8000/api/actions/act_.../reject \
  -H "Content-Type: application/json" -d '{"customer_id":"cus_orbit_001"}'
```

Unknown or cross-customer actions return the same non-leaking 404. An unresolved MCP
execution returns sanitized 503 `action_execution_unavailable`; retry is safe. Live
chat/proposal uses OpenAI. Approval and rejection do not call OpenAI.

## Tests and validation

The normal suite is deterministic and makes no OpenAI or PostgreSQL calls:

```bash
python -m pytest
python -m compileall -q src tests
python -m pip check
python -m service_desk.evaluation.run validate
python -m build --wheel
```

Opt-in integrations use deterministic data and make no OpenAI calls:

```bash
RUN_POSTGRES_TESTS=1 python -m pytest -m postgres
RUN_MCP_TESTS=1 python -m pytest -m mcp
```

PowerShell uses `$env:RUN_POSTGRES_TESTS='1'` and `$env:RUN_MCP_TESTS='1'`. The MCP
marker includes a real Streamable HTTP round trip. PostgreSQL tests cover concurrency,
receipts, retries, restarts, rejection, expiry, ownership, and audit persistence. CI
runs the offline path.

## Evaluation and benchmark integrity

Held-out JSON is frozen by normalized SHA-256 fingerprints before live use. Observed
sets and first reports are immutable. Offline modes never call OpenAI; explicit live
modes require `--confirm-live`.

```bash
python -m service_desk.evaluation.run validate
python -m service_desk.evaluation.run workflow-offline --split held_out --workflow-version v3
python -m service_desk.evaluation.run action-offline --split held_out --action-version v2

# Paid/manual development modes:
python -m service_desk.evaluation.run retrieval-live --split development --confirm-live
python -m service_desk.evaluation.run workflow-live --split development --limit 1 --confirm-live
python -m service_desk.evaluation.run action-live --split development --confirm-live
```

Live action evaluation creates isolated fixtures, refuses to overwrite residue from
an incomplete run, executes decisions through MCP, records sanitized output, and
removes only its exact identities afterward.

### Recorded results

- Retrieval held-out v1 (6 cases, top 4): Hit@1 **1.0**, Hit@4 **1.0**, MRR **1.0**.
- V2 workflow v1: historical partial/resumed run, 4/6 unique outcomes; it exposed
  bounded synthesis and a questionable mixed expectation.
- V2 workflow v2: 3/6, route accuracy 0.5; it exposed routing taxonomy gaps.
- V2 workflow v3: final unseen post-fix run, 6/6 with all measured checks passing.
- V3 action v1: first run 5/6; all five safety cases passed, but a valid clarification
  plus detected write intent was incorrectly rejected by validation.
- V3 action v2: new unseen post-fix run, **6/6**; route, intent, proposal,
  pre-approval non-mutation, terminal state, mutation, replay, and all five applicable
  safety checks passed.

Manual review of the final workflow answers found clear separation between account
facts and KB guidance. Manual review of action v2 found that every answer clearly
described the action as pending before approval; approved actions mutated the intended
isolated ticket exactly once, rejection caused no mutation, the cross-workspace case
did not leak or mutate, and clarification/hypothetical cases created no action.

These small synthetic benchmarks validate listed contracts; they do not establish
general 100% accuracy or calibrated confidence.

## Known V3 limitations

- `customer_id` is caller-supplied. It is an ownership guard, **not production
  authentication or authorization**.
- MCP is localhost-only and has no production OAuth/service identity in V3.
- Approval executes synchronously. Ambiguous failures are retryable, but there is no
  background reconciliation worker or operator dashboard.
- Pending actions cannot be edited; reject and request a new action instead.
- Ticket scope is intentionally narrow. No payment writes or generic CRUD exist.
- Dense retrieval has no hybrid search/reranker; the corpus is only 20 chunks.
- Model behavior remains probabilistic; broader adversarial and load testing belongs
  beyond this portfolio V3.

## Roadmap after V3

Potential later work includes real identity/OAuth, background reconciliation,
broader observability, and a reviewer UI. Those are deliberately outside V3.
