---
document_id: KB-SUP-003
title: Resetting a Harborlight Workspace password
domain: support
product: Harborlight Workspace
---

# Password reset

Use password reset only for an account that signs in with an email address and
password. If your organization requires SSO, reset your password through the
organization identity provider instead; Harborlight cannot create a local
password for an SSO-only account.

## Reset steps

1. Open the Harborlight Workspace sign-in page.
2. Select **Forgot password**.
3. Enter your exact sign-in email address.
4. Open the reset email and follow the link.
5. Set a new password, then sign in again.

For security, the confirmation page always displays a generic success message.
It does not reveal whether an email address has an account.

## Link rules

Reset links expire after 15 minutes and can be used once. Requesting another
reset invalidates older reset links. Harborlight allows up to five reset emails
per account per hour; additional requests are delayed to reduce abuse.

Use the newest email. If the link reports that it is expired or already used,
request a new reset rather than retrying the old link. Do not forward reset
emails, because anyone with the link could change the password before it
expires.

## Password requirements

Passwords must be at least 12 characters. Harborlight blocks common breached
passwords and passwords that contain the user’s email address. A long passphrase
with unrelated words is generally easier to remember and stronger than a short,
complex-looking password.

Changing a password ends existing browser sessions for that account. API keys
are separate credentials and are not changed by a password reset; rotate any
key only if you believe it was exposed.

## If the email does not arrive

Wait a few minutes, check spam and corporate quarantine, and verify the email
address. If your company filters automated mail, ask the mail administrator to
allowlist Harborlight Workspace messages. Repeated requests do not make delivery
faster and can reach the hourly limit.

## If you are locked out

Ten unsuccessful password attempts within 30 minutes create a 30-minute
temporary lock. Wait for the lock to end, then request one fresh reset link.
If you can sign in but no longer see the workspace, this is a membership issue,
not a password issue; ask a workspace Owner or Admin to check your membership.

## Security warning

Harborlight Support will never ask you to send a reset link, password, MFA code,
or API key. If you receive an unexpected reset email, do not use the link; change
your password from the normal sign-in page if you suspect an account problem.
