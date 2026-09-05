---
document_id: KB-SUP-002
title: Signing in and recovering workspace access
domain: support
product: Harborlight Workspace
---

# Account access

Harborlight Workspace accounts are personal. Each person signs in with their
own email address and authentication method, then selects a workspace they are
allowed to access. Being invited to a workspace does not grant access until the
invitation is accepted.

## Sign-in methods

Workspaces can use email-and-password sign-in, organization single sign-on
(SSO), or both. The sign-in page shows the available method after the user enters
their work email address. If the workspace requires SSO, password sign-in is not
offered for that workspace.

Use the same email address that received the invitation. Changing the display
name does not change the sign-in address. If a user belongs to several
workspaces, they sign in once and switch workspaces from the workspace menu.

## Locked or blocked sign-in

After 10 unsuccessful password attempts in 30 minutes, password sign-in is
temporarily locked for 30 minutes. This protects accounts from repeated guessing.
Password reset requests do not bypass the lock; wait for it to expire, then use
the reset flow.

For SSO users, Harborlight can only confirm that the identity provider did not
complete sign-in. The user’s organization administrator must check the identity
provider assignment, email claim, and multi-factor authentication policy.

## Lost access to a workspace

First confirm that the correct workspace is selected. A user may successfully
sign in but see no workspace if an Owner or Admin removed their membership. Ask
an Owner or Admin to check **Workspace settings → Members** and send a new
invitation if needed.

If the workspace is billing-restricted, members can still sign in but may be
unable to create new work items or change settings. This is different from an
account-access failure; an Owner or Billing Admin should resolve the unpaid
invoice.

## Safe recovery steps

1. Confirm the email address and preferred sign-in method.
2. Try a private browser window to avoid an old SSO session.
3. Request a password reset only for password-enabled accounts.
4. Check the invitation status with a workspace Owner or Admin.
5. For SSO, contact the organization identity administrator before opening a
   Harborlight ticket.

## What Support can verify

Support can help identify an expired invitation, workspace membership state, or
general service issue after verifying the requester’s identity. Support cannot
tell a requester another user’s password, bypass an organization’s SSO policy,
or transfer workspace ownership without appropriate authorization.

Never send a password, reset code, MFA code, API key, or full identity document
in a support ticket. Harborlight staff will not ask for those secrets.
