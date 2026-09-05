---
document_id: KB-TEC-005
title: Common API errors and diagnostic fields
domain: technical
product: Harborlight Workspace
---

# Common API errors

Harborlight Workspace API error responses use JSON and include an
`X-Request-ID` header. Record that request ID when contacting Support. It lets
Harborlight find the request without receiving an API key or confidential body.

## Response format

```json
{
  "error": {
    "code": "rate_limit_exceeded",
    "message": "Too many requests. Retry after 12 seconds.",
    "request_id": "req_example"
  }
}
```

The exact message can change, so integrations should use HTTP status and stable
error code rather than matching human-readable text.

## Error table

| Status | Typical code | Meaning | First action |
|---:|---|---|---|
| 400 | `invalid_request` | Malformed JSON, unsupported parameter, or invalid filter. | Validate request structure. |
| 401 | `authentication_failed` | Missing, revoked, or unknown API key. | Check the Bearer key safely. |
| 403 | `permission_denied` | Valid key lacks permission or entitlement. | Use the narrow correct key or change workspace role. |
| 404 | `not_found` | Resource does not exist in this workspace or is not visible. | Check ID and workspace context. |
| 409 | `conflict` | Request conflicts with current state or version. | Fetch current state, then retry intentionally. |
| 413 | `payload_too_large` | Body exceeds endpoint size limit. | Reduce payload or split work. |
| 422 | `validation_failed` | Fields are well-formed JSON but fail business validation. | Inspect field-level details. |
| 429 | `rate_limit_exceeded` | Key exceeded rate capacity. | Honor `Retry-After`. |
| 500/502/503 | `service_unavailable` | Temporary Harborlight service issue. | Retry idempotent requests with backoff. |

## Important distinctions

A `401` is about authentication. A `403` means authentication succeeded but the
key cannot perform that action. A `404` can deliberately be returned instead of
a `403` when revealing a resource’s existence would leak workspace information.

A `409` is not a signal to blindly retry. For example, two administrators may
try to update the same setting. Retrieve the current resource, decide whether
the intended change still makes sense, then submit a new request.

## Safe diagnostics

Log the endpoint, method, status, stable error code, request ID, and retry
headers. Redact Authorization headers, webhook signatures, passwords, and any
personal content. For a failed POST or PATCH, log only a safe summary of fields
unless your own data-handling policy explicitly permits more.

## When to contact Support

Provide the request ID, approximate timestamp in UTC, workspace name, endpoint,
status code, and a redacted response. For persistent `429`, include traffic
shape and retry behavior. For `5xx`, check the Harborlight status page first;
if an incident is listed, subscribe rather than opening duplicate tickets.
