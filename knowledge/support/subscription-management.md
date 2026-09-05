---
document_id: KB-SUP-004
title: Managing a workspace subscription
domain: support
product: Harborlight Workspace
---

# Subscription management

Subscription controls are in **Workspace settings → Billing**. They are separate
from ordinary workspace administration because plan changes, payment methods,
and invoice history can affect the organization financially.

## Who can do what

| Action | Owner | Billing Admin | Admin | Member / Viewer |
|---|---|---|---|---|
| View current plan | Yes | Yes | Yes | No |
| View invoices | Yes | Yes | No | No |
| Change payment method | Yes | Yes | No | No |
| Upgrade or schedule downgrade | Yes | Yes | No | No |
| Cancel subscription | Yes | Yes | No | No |
| Manage ordinary members | Yes | No | Yes | No |

An Owner can assign a Billing Admin role to a trusted person. Billing Admins do
not gain project administration, member removal, or ownership-transfer rights.

## Change a plan

Open **Billing → Plan**, select Starter, Growth, or Scale, and review the
effective date before confirming. Upgrades take effect immediately and can
create a prorated invoice. Downgrades are scheduled for the next renewal date
and require the workspace to fit the target plan’s limits first.

The plan page also shows included billable seats: Starter has 3, Growth has 10,
and Scale has 25. Owners and Billing Admins should review the active billable
seat count before scheduling a downgrade.

## Manage payment and invoices

Use **Billing → Payment methods** to add or replace the default card. Use
**Billing → Invoices** to view issued invoices, due dates, payment state, and
downloadable receipts. Do not paste card information into a support ticket.

If an invoice is past due, updating the default payment method triggers an
immediate retry while the invoice remains open. The workspace may have a
seven-day past-due grace period before billing restrictions apply.

## Cancel a subscription

Cancellation is scheduled for the next renewal date. It does not immediately
remove access and does not refund the current billing period. After cancellation
takes effect, the workspace remains read-only for 30 days so an Owner can export
permitted data. Invoice and ticket history remain available according to normal
record retention.

## Troubleshooting

If the Billing menu is missing, verify that you are an Owner or Billing Admin
and that you selected the correct workspace. If a downgrade cannot be saved,
reduce billable seats or resolve other target-plan overages first. If a plan
change invoice looks wrong, compare the effective date and remaining billing
period before contacting Billing with the invoice ID.
