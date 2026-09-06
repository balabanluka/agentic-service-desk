# Agentic Service Desk

A production-oriented, fictional SaaS service desk built with Python, FastAPI,
LangGraph, OpenAI, and Pydantic.

## V1

V1 is a small, controlled agentic system. A single LangGraph orchestrator routes
a request to one of three bounded workflows: support, billing, or technical.
Within its selected workflow, the model can choose from a strict, read-only
allowlist of local business tools. The graph—not the model—controls routing,
workflow boundaries, permissions, and the bounded tool-use loop.

Each domain workflow is a terminal graph node: after its bounded tool-use loop,
the model composes the final grounded answer within that workflow. V1
intentionally has no separate `compose_answer` node. The clarification and
missing-customer terminal nodes return safe template answers.

The only business data is original synthetic local data. V1 has no write
actions, RAG answer generation, MCP, Langfuse, frontend, or external
business-system integration.

### API

- `GET /health`
- `POST /api/chat`

`POST /api/chat` accepts a `customer_id` and a message. Its response includes
the answer plus execution metadata such as the selected route, graph path, and
tools used.

### Local development

Use Python 3.12 and install the development extra:

```bash
python -m pip install -e ".[dev]"
pytest
uvicorn service_desk.main:app --reload
```

Copy `.env.example` to a local `.env` and set an OpenAI key only when running
the live application. V1 defaults to `gpt-5.6-luna`; override it with
`OPENAI_MODEL` when needed. The test suite injects an offline fake model gateway
and never makes real OpenAI calls.

## V2 knowledge database infrastructure

V2 currently provides frozen synthetic knowledge documents, deterministic
chunking, local PostgreSQL/pgvector persistence primitives, and explicit
idempotent ingestion, exact cosine retrieval, and route-scoped grounded RAG
context for the V1 workflows. It does not add autonomous agents, write actions,
or automatic knowledge ingestion.

Copy `.env.example` to a local `.env`, choose a local PostgreSQL password, then
start only the database service and apply the versioned schema migration:

```bash
docker compose up -d postgres
python -m service_desk.knowledge.migrate
```

PostgreSQL is bound to `127.0.0.1` only and stores its data in the named Docker
volume `agentic_service_desk_postgres_data`. Keep `.env`, Docker volumes, and
generated data out of version control.

When intentionally ready to make a live OpenAI embeddings call, run:

```bash
python -m service_desk.knowledge.ingest
```

This command is never run automatically by FastAPI or pytest. It embeds only
new or changed chunk content and prints a metadata-only ingestion report.

To explicitly retrieve passages, use the same configured embedding model and
database:

```bash
python -m service_desk.knowledge.search "Why do CSV exports time out for large reports?" --domain technical
```

Retrieval searches active chunks for the configured embedding model with exact
pgvector cosine ranking. Its cosine similarity is a ranking signal, **not** a
calibrated confidence score or answer-quality guarantee.

When configured with both an OpenAI key and `DATABASE_URL`, the V1 graph
retrieves a small, fixed-domain context for its selected support, billing, or
technical workflow. The model cannot choose the retrieval domain. Final
workflow answers receive both that context and the existing scoped business
tool results; API execution metadata exposes only concise source identifiers,
never retrieved vectors or full chunks.

## Roadmap

- **V2 next:** authenticated customer context and retrieval/grounding evaluation.
- **V3:** MCP integrations, human approval for sensitive/write actions, and
  richer evaluation and observability.
