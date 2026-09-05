---
document_id: KB-SUP-006
title: Support ticket priorities and response targets
domain: support
product: Harborlight Workspace
---

# Support ticket priorities

Harborlight Support uses priorities to order investigation work. Priority is
based on business impact, number of affected users, and whether a practical
workaround exists. A priority is a response target, not a guaranteed resolution
time.

## Priority levels

| Priority | Use when | Initial response target |
|---|---|---|
| P1 Critical | A full workspace is unavailable or there is a confirmed security-impacting incident. | 1 hour, 24/7 |
| P2 High | A major function is unavailable for many users and no reasonable workaround exists. | 4 business hours |
| P3 Normal | A feature is impaired for some users or a workaround exists. | 1 business day |
| P4 Low | How-to questions, minor defects, feedback, or cosmetic issues. | 3 business days |

Ticket records use the matching priority values `critical` (P1), `high` (P2),
`normal` (P3), and `low` (P4). Status values such as `open`, `in_progress`,
and `resolved` describe ticket progress separately from priority.

Business hours are Monday–Friday, 09:00–17:00 in the workspace support region,
excluding local public holidays. P1 is handled continuously because a broad
outage cannot wait for the next business day.

## Good examples

- **P1:** every user in several workspaces receives errors when opening the
  product, and the status page confirms an active incident.
- **P2:** CSV export fails for all Growth-plan users, with no available manual
  export path.
- **P3:** one team cannot update a webhook endpoint, but other workspace work
  continues.
- **P4:** a user asks how to invite a Viewer or requests a future report format.

An individual forgotten password is normally P3, not P1, because the user can
use the documented reset flow or ask an Owner to confirm access. An overdue
invoice is normally a billing request, not an incident ticket.

## What to include in a ticket

Provide the workspace name, affected feature, start time with timezone, number
of affected users, exact error text, relevant request ID, and steps that
reproduce the issue. For API issues, include the endpoint, HTTP status, and
redacted response body. Do not include passwords, reset links, API keys,
webhook secrets, or payment-card details.

## Reprioritization

Support may raise or lower priority as evidence changes. For example, a report
that initially affects one person may become P2 after confirming a broader
outage. Conversely, a P2 report can become P3 when a documented workaround is
available.

## Following an active incident

Check the Harborlight status page before opening duplicate P1 tickets. If an
incident is already listed, subscribe for updates and add only workspace-specific
impact that the incident team needs. This keeps investigation channels focused
while preserving a record of affected customers.
