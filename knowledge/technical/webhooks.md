---
document_id: KB-TEC-004
title: Webhook delivery, signatures, and retries
domain: technical
product: Harborlight Workspace
---

# Webhooks

Webhooks notify an external HTTPS endpoint when selected Harborlight Workspace
events occur. They are best for integrations that need near-real-time changes
without frequent API polling.

## Create a webhook

Only a workspace Owner can create, edit, pause, or delete webhook subscriptions.
Choose an HTTPS endpoint, select event types, and save the generated signing
secret in a server-side secret store. A webhook subscription belongs to one
workspace; it does not receive events from other workspaces.

Common event families include record creation or update, member changes, export
completion, and incident notifications. Configure only the events your endpoint
needs to reduce unnecessary traffic.

## Verify signatures

Each delivery includes:

```text
X-Harborlight-Event: record.updated
X-Harborlight-Delivery: evt_...
X-Harborlight-Timestamp: 2026-09-01T10:15:00Z
X-Harborlight-Signature: v1=...
```

Compute an HMAC-SHA256 signature from the timestamp, a period, and the exact raw
request body using the webhook signing secret. Compare it with the signature
using a constant-time comparison. Reject timestamps older than five minutes to
reduce replay risk.

Do not parse and reserialize JSON before checking the signature. A harmless
formatting change can produce a different byte sequence and invalidate the
signature.

## Delivery and retries

Your endpoint should return a `2xx` status within 10 seconds. Harborlight treats
any other status, timeout, or connection failure as unsuccessful. Failed events
are retried up to 10 times over roughly 24 hours with increasing delays.

Delivery is at least once, not exactly once. Store `X-Harborlight-Delivery` and
make processing idempotent so a retried event does not create duplicate work.
Events can arrive out of order; use the event timestamp or fetch the latest
record from the API when order matters.

## Security and operations

Use a public HTTPS endpoint with a valid certificate. Do not use a webhook
endpoint to expose an internal admin panel. Rotate the signing secret by creating
a replacement subscription, validating it, then deleting the old one. Treat the
secret like an API key and never include it in support tickets.

## Troubleshooting

Check the webhook delivery log for status, response time, and delivery ID.
Confirm DNS, TLS, firewall rules, signature verification, and a prompt 2xx
response. A `429` from your endpoint will be retried, but repeatedly rate
limiting Harborlight can exhaust the delivery window. If needed, accept the
event quickly and queue work internally.

## Event payload handling

Webhook payloads contain an event type, delivery ID, timestamp, workspace ID,
and a resource summary. They are notifications, not permanent record history.
When an integration needs the latest full state, verify the signature and then
retrieve the resource through the API using an appropriate read key. This avoids
making incorrect assumptions when later events arrive before earlier deliveries
are processed.
