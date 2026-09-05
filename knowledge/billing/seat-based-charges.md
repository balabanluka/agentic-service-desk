---
document_id: KB-BIL-006
title: Seat-based charges and billable roles
domain: billing
product: Harborlight Workspace
---

# Seat-based charges

Harborlight Workspace charges for billable seats in addition to the seats
included with the selected plan. A billable seat is assigned to a person with an
**Owner**, **Admin**, or **Member** role. A **Viewer** can view permitted work
but does not consume a paid seat. Role capabilities are described in the
account-roles guide.

## Included seats

Starter includes 3 billable seats, Growth includes 10, and Scale includes 25.
If a Growth workspace has 12 active billable users, it has two additional seats.
The workspace billing page shows included seats, active billable seats, and any
scheduled seat changes separately.

An invitation does not consume a seat until the invited person accepts and is
given a billable role. Changing a Viewer to Member consumes a seat immediately;
changing a Member to Viewer releases the seat for the next regular renewal.

## Adding seats

Adding a billable user above the included or already purchased quantity creates
a prorated charge for the remaining billing period. On a monthly plan, a Member
added with 10 days left in a 30-day period is charged for roughly one third of
that seat’s monthly price. On annual plans, the same principle applies using the
remaining annual term.

The incremental charge may appear on a separate open invoice. For card-backed
workspaces, it can be collected automatically. It does not change the plan
renewal date or alter other seat assignments.

## Removing seats

Removing a member, converting them to Viewer, or reducing a purchased-seat
quantity affects the next regular renewal. Harborlight does not issue a
mid-period refund for unused seat time. This rule also applies when a person
leaves the company midway through a billing period.

To avoid an accidental future charge, remove or downgrade the user before the
next billing anchor date. Owners and Billing Admins can see the upcoming seat
quantity; Admins can manage members but cannot confirm billing changes.

## Common questions

### Why am I charged when someone was only invited?

Check whether the invitation was accepted and whether the role is Owner, Admin,
or Member. Pending invites and Viewers do not consume billable seats.

### Why did the count not drop immediately?

Access changes take effect immediately, but the financial reduction is scheduled
for the next renewal. The current paid seat remains available until then.

### Can I share one seat?

No. Each active person needs their own account. Shared credentials are not
supported because they weaken access controls, audit records, and API security.

## Troubleshooting checklist

Compare the active role list with the billing seat list, check pending invites,
review scheduled changes, then compare the invoice’s seat line items with the
billing period dates. Contact Billing with the invoice ID and affected member
emails if the count still appears incorrect.
