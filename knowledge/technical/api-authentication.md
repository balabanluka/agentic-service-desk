---
document_id: KB-TEC-001
title: API authentication and workspace API keys
domain: technical
product: Harborlight Workspace
---

# API authentication

Harborlight Workspace API requests use workspace API keys. An API key is tied to
one workspace and one permission set; it is not a user password and must never
be shared in tickets, browser screenshots, or client-side code.

## Create a key

Only a workspace Owner can create, rename, rotate, or revoke a workspace API
key. Go to **Workspace settings → Integrations → API keys**, choose a purpose,
select the required permission set, and copy the key immediately.

The full key is shown once. Harborlight stores only a protected representation,
so a lost key cannot be displayed again. Create a replacement and revoke the old
key after dependent systems are updated.

## Send the key

Use the HTTP Authorization header:

```http
Authorization: Bearer hlw_live_example_redacted
```

Use HTTPS for every request. Do not send keys in a query parameter, URL path,
browser local storage, or plain-text configuration committed to source control.
Server-side environment variables or a dedicated secret manager are preferred.

## Permission sets

| Permission set | Intended capability |
|---|---|
| Read | Retrieve workspace data allowed by the API. |
| Manage | Create or update supported workspace resources. |
| Webhook | Manage webhook subscriptions only. |

Choose the narrowest permission set. A webhook-only key should not be used by a
reporting integration, and a read key should not be used by a deployment system
that needs to update records.

## Authentication responses

- `401` means the key is missing, malformed, revoked, or unknown.
- `403` means the key is valid but lacks the required permission or workspace
  entitlement.
- `429` means the key exceeded an API rate limit; wait for the reset time.

All API errors include an `X-Request-ID` header. Include that value in a support
ticket instead of sending the API key.

## Rotation procedure

1. Create a new key with the same minimum required permission set.
2. Store it in the integration’s secret store.
3. Deploy or restart the integration using the new key.
4. Verify one successful request and correct workspace identity.
5. Revoke the old key.

Do not revoke the old key before the replacement is live unless you believe it
is exposed. If exposure is suspected, revoke it immediately, create a new key,
and review integration logs for unexpected requests.

## Troubleshooting

Confirm that the Authorization header has exactly one `Bearer` token, that the
key belongs to the intended workspace, and that the endpoint matches its
permission set. A password reset does not change API keys. If a key works in one
workspace but not another, create a key in the target workspace rather than
reusing it.
