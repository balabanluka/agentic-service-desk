# Agentic Service Desk

A production-oriented, fictional SaaS service desk built with Python, FastAPI,
LangGraph, OpenAI, and Pydantic.

## V1

V1 is a small, controlled agentic system. A single LangGraph orchestrator routes
a request to one of three bounded workflows: support, billing, or technical.
Within its selected workflow, the model can choose from a strict, read-only
allowlist of local business tools. The graph—not the model—controls routing,
workflow boundaries, permissions, and the bounded tool-use loop.

The only business data is original synthetic local data. V1 has no write
actions, RAG, vector database, MCP, Langfuse, frontend, Docker service, or
external business-system integration.

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
the live application. The test suite injects an offline fake model gateway and
never makes real OpenAI calls.

## Roadmap

- **V2:** retrieval-augmented knowledge access and authenticated customer
  context.
- **V3:** MCP integrations, human approval for sensitive/write actions, and
  richer evaluation and observability.
