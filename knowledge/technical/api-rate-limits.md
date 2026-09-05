---
document_id: KB-TEC-002
title: API rate limits and retry behavior
domain: technical
product: Harborlight Workspace
---

# API rate limits

Harborlight Workspace rate limits protect shared service capacity. Limits apply
per workspace API key and are measured in rolling one-minute windows. They are
not a quota of billable seats and do not change when an individual user signs in
or out.

## Standard limits

| Plan | Sustained limit | Short burst limit |
|---|---:|---:|
| Starter | 120 requests/minute | 20 requests/second |
| Growth | 600 requests/minute | 60 requests/second |
| Scale | 2,400 requests/minute | 200 requests/second |

The lower of the sustained or burst rules applies. For example, a Growth key can
send many requests across a minute but cannot send 100 at once in a single
second. Export creation and webhook management use the same API key limits;
large exports are asynchronous and should not be polled continuously.

## Rate-limit response

When a limit is exceeded, the API returns:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 12
X-RateLimit-Limit: 600
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 2026-09-01T10:15:00Z
```

`Retry-After` is the preferred wait time in seconds. `X-RateLimit-Reset` is an
ISO-8601 timestamp indicating when capacity is expected to return. Header values
are advisory; clients should still handle another 429 after retrying.

## Recommended retry strategy

For a `429`, wait for `Retry-After` and retry once. For repeated 429 responses,
use exponential backoff with jitter, for example 2, 4, 8, then 16 seconds plus a
small random delay. Do not retry hundreds of requests simultaneously when the
window resets; queue them gradually.

For `500`, `502`, or `503`, retry only idempotent requests. GET requests are
idempotent. For create or update requests, use the API’s idempotency key when
the endpoint supports it; otherwise confirm whether the first request completed
before sending it again.

## Avoiding unnecessary traffic

- Cache stable workspace metadata for a short period.
- Request only fields needed by the integration.
- Use webhooks for changes instead of frequent polling.
- Poll export jobs no more than once every 10 seconds.
- Batch independent reads where the endpoint supports pagination.

## Troubleshooting

Record the endpoint, workspace, response status, `X-Request-ID`, and rate-limit
headers. Do not send the API key. If a rate limit is consistently too low for a
valid Scale use case, contact Support with traffic patterns and whether webhooks
or caching have already been considered.
