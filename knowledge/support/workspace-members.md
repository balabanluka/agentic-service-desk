---
document_id: KB-SUP-001
title: Managing workspace members and invitations
domain: support
product: Harborlight Workspace
---

# Workspace members and invitations

A Harborlight Workspace is a shared area for one team or organization. Members
belong to a workspace, not merely to an individual project. Owners and Admins
can invite people and change ordinary member roles; only Owners and Billing
Admins can approve changes that affect billing.

## Invite a member

1. Open **Workspace settings → Members**.
2. Select **Invite member**.
3. Enter one or more work email addresses.
4. Choose a role: Admin, Member, or Viewer.
5. Send the invitation.

Invitations expire after 14 days. If an invite expires, create a new invitation;
the old link cannot be reactivated. A person who already belongs to the
workspace cannot receive a second active invitation.

## Which roles use a seat

Owners, Admins, and Members are billable roles. Viewers are non-billable and
can only view information they have been permitted to see. A pending invitation
does not consume a seat until it is accepted with a billable role.

Adding a billable person above the workspace’s included or purchased seats can
create a prorated charge. Removing a billable person changes future renewal
quantity but does not refund the current billing period. See the seat-based
charges policy for billing timing.

## Remove or deactivate a member

An Owner or Admin can remove a Member or Viewer from **Members**. Removal ends
their workspace access immediately, including browser sessions and API sessions
created with that person’s personal credentials. Their historical comments and
activity remain attached to their name for audit continuity.

An Admin cannot remove the last Owner. Before an Owner leaves, another existing
billable user must become Owner. If the workspace has only one Owner, contact
Support with the workspace name and proof of authority to transfer ownership.

## Common invitation problems

### The recipient did not receive the email

Ask the recipient to check spam or quarantine folders and confirm the spelling.
Resend only after waiting a few minutes; repeated sends do not create separate
accounts. Corporate mail filters sometimes block automated invitation messages,
so allowlist the Harborlight Workspace sending domain if necessary.

### The invitation says the email is already in use

The person may already have a Harborlight account for another workspace. They
should sign in using that account and accept the invitation. One person can
belong to multiple workspaces with the same sign-in email.

### There are no available seats

An Owner or Billing Admin must add seats or choose the Viewer role. Changing a
role to Viewer does not grant edit access, so use it only when read-only access
is appropriate.

## Good practice

Use named accounts, review members after staffing changes, and keep at least two
Owners for business continuity. Do not share passwords or use a shared mailbox
as a member account; both practices make access recovery and audit history less
reliable.
