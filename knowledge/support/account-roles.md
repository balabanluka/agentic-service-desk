---
document_id: KB-SUP-005
title: Workspace account roles and permissions
domain: support
product: Harborlight Workspace
---

# Account roles

Harborlight Workspace uses four workspace-level roles. Roles control what a
person can see and change inside one workspace. They do not transfer between
workspaces: a person can be an Owner in one workspace and a Viewer in another.

## Role summary

| Role | Main purpose | Billable seat |
|---|---|---|
| Owner | Full workspace control and business continuity. | Yes |
| Admin | Manages workspace configuration and members. | Yes |
| Member | Works with permitted projects, requests, and records. | Yes |
| Viewer | Read-only access to permitted information. | No |

## Owner

Owners can manage members, workspace settings, billing, integrations, API keys,
and subscription changes. A workspace must always have at least one Owner.
Owners can assign another Owner before leaving, but an Admin cannot remove the
last Owner.

Keep at least two Owners where possible. This prevents a single departed or
unavailable employee from blocking billing, access recovery, or cancellation.

## Admin

Admins can manage ordinary members, workspace settings, and operational
configuration. They cannot change payment methods, see invoices, cancel the
subscription, or transfer ownership. Admins are useful for daily workspace
operations without giving finance access.

## Member

Members can create and update work within projects they are permitted to use.
They can use normal product features but cannot manage workspace billing,
membership, global API keys, or ownership. Members consume a billable seat.

## Viewer

Viewers can read content they have been granted access to. They cannot edit
records, invite members, change configuration, or access billing. Viewers do
not consume a billable seat, which makes them suitable for auditors or
stakeholders who only need visibility.

## Billing Admin permission

Billing Admin is an additional billing permission assigned by an Owner; it is
not a fifth workspace role. A Billing Admin can view invoices, change payment
methods, and manage plan or cancellation requests, but does not automatically
gain Admin, Member, or Viewer project access. The person still has one of the
four roles above, which determines normal product access and whether they
consume a seat.

## Role changes

Owners and Admins can change Members and Viewers. Only an Owner can assign or
remove the Owner and Billing Admin roles. Promoting a Viewer to a billable role
can create a prorated seat charge if the workspace exceeds its included seats.
Demoting a billable role to Viewer changes access immediately but reduces billing
only at the next renewal.

## Troubleshooting permissions

If a user can sign in but cannot see a button, first check the workspace and
role. If they can see a project but cannot edit it, project-level permissions may
be more restrictive than their workspace role. Never solve a narrow access issue
by making every user an Owner; grant the smallest role needed for the task.
