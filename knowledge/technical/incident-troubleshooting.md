---
document_id: KB-TEC-006
title: Incident troubleshooting and service-impact checks
domain: technical
product: Harborlight Workspace
---

# Incident troubleshooting

Use this guide when Harborlight Workspace appears unavailable, slow, or
inconsistent for multiple users. Start by distinguishing a broad service issue
from a local browser, network, role, billing, or integration problem.

## First five minutes

1. Check the Harborlight status page for an active incident or maintenance.
2. Confirm the workspace name, feature affected, and the exact start time in
   timezone-aware form.
3. Test in a private browser window or a second supported browser.
4. Ask whether another user in the same workspace sees the same problem.
5. For API failures, capture the HTTP status and `X-Request-ID`.

Do not clear browser data, rotate API keys, or change billing settings until you
know whether the problem is broad. Those changes can remove useful evidence or
create a second issue.

## Classify the symptom

| Symptom | Likely first check |
|---|---|
| Everyone cannot sign in | Status page, SSO provider, network reachability. |
| One person cannot sign in | Password reset, SSO assignment, membership. |
| Workspace is read-only | Past-due billing banner and invoice state. |
| API returns 401/403 | API key, permission set, workspace context. |
| API returns 429 | Retry schedule and traffic burst. |
| CSV export delays | Export job status and plan row limit. |
| Webhooks fail | Endpoint TLS, signature verification, response time. |

## Gather useful evidence

For a browser issue, collect the workspace, affected page, approximate time,
browser version, visible error text, and whether private browsing reproduces it.
For an API issue, collect method, endpoint, status, request ID, and redacted
response. For a webhook issue, collect delivery ID and endpoint response status.

Never attach passwords, API keys, webhook signing secrets, reset links, MFA
codes, payment-card details, or unrestricted log files.

## Practical workarounds

If a non-critical page is slow, retry once after a short wait and avoid repeated
refreshes. If an export is processing, poll no more than once every 10 seconds
or wait for a completion webhook. If a webhook endpoint is overloaded, return a
quick 2xx after safely queueing the event internally. If a billing restriction
is shown, an Owner or Billing Admin should update the payment method rather than
opening a technical outage ticket.

## Escalation

Use P1 only for a confirmed broad outage, severe security impact, or an entire
workspace being unavailable without a workaround. Use P2 for a major function
affecting many users with no workaround. Other issues are normally P3 or P4.
Include impact, number of affected users, start time, reproduction steps, and
safe diagnostic IDs. Priority sets response expectations; it is not a promise
of immediate resolution.
