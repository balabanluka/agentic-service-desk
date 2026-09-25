# Evaluation data and integrity

This directory contains original synthetic development and frozen held-out datasets
for Harborlight Workspace.

- Retrieval datasets measure exact pgvector ranking.
- Workflow datasets measure V2 routing, tools, grounding, clarification, and safety.
- Action datasets measure V3 write intent, proposal gating, pre-approval
  non-mutation, approval/rejection, exactly-once receipts, ownership, and audit.

Development data may guide implementation. Held-out files are frozen by normalized
UTF-8 SHA-256 fingerprints before their first live run. Observed datasets and first
reports are never rewritten to improve scores. A product fix motivated by an observed
set requires a new unseen version.

Historical V2 workflow v1/v2/v3 and retrieval v1 remain unchanged. V3 action v1 is
the historical pre-fix run; action v2 is the final unseen post-fix set. Untracked local
development reports stay ignored. Intentionally tracked held-out reports and summaries
contain only synthetic, sanitized data.

Offline commands never call OpenAI:

```bash
python -m service_desk.evaluation.run validate
python -m service_desk.evaluation.run action-offline --split held_out --action-version v2
```

Live modes require `--confirm-live`, OpenAI, PostgreSQL, and the ticket MCP service.
Action fixtures are isolated and cleaned by exact identities.
