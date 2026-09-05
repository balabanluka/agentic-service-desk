---
document_id: KB-BIL-005
title: Billing cycles, renewal dates, and invoice timing
domain: billing
product: Harborlight Workspace
---

# Billing cycles and renewal dates

Harborlight Workspace subscriptions are either monthly or annual. Every
workspace has a billing anchor date set when the paid subscription begins. The
anchor determines when the next regular invoice is issued; it is not changed by
adding seats or upgrading a plan.

## Monthly subscriptions

Monthly subscriptions renew on the same calendar day each month. A workspace
started on 12 April renews on the 12th of later months. If the anchor is the
29th, 30th, or 31st and a month does not contain that date, renewal occurs on
the final calendar day of that month, then returns to the original anchor when
possible.

Example: a workspace started on 31 January renews on 28 February in a
non-leap year, 31 March, and 30 April.

## Annual subscriptions

Annual subscriptions renew once every 12 months on their annual anchor date.
They receive one regular annual invoice. Annual workspaces can still receive a
separate prorated invoice for an immediate upgrade or newly added seats.

## Invoice timing

A standard renewal invoice is issued on the billing anchor date and is due 14
calendar days later. Card-backed workspaces begin automatic payment collection
when the invoice is issued. Manual-payment workspaces follow the payment
instructions on the invoice. Invoice states and automatic retries are described
in the invoice-status and failed-payment documents.

The displayed renewal date is the date the next subscription period begins. It
is not necessarily the date on which a card statement shows the charge: banks
can post a completed payment one or more days later.

## Billing timezone and currency

The workspace billing timezone controls date boundaries for invoices, renewal,
and due dates. Changing a user’s personal timezone does not change billing.
The billing currency is selected when the subscription begins and cannot be
changed from the workspace UI. To change currency, an Owner should contact
Billing before the next renewal; the request may require a new subscription.

## Edge cases

An immediate plan upgrade creates a separate prorated charge and does not move
the next regular renewal. A scheduled downgrade takes effect on the next renewal
date and therefore does not alter the current invoice. Removing seats reduces a
future renewal charge; it does not recalculate a previously issued invoice.

If a workspace is billing-restricted when renewal occurs, the new invoice still
exists and follows the normal collection process. Restoring payment restores the
workspace; it does not create a second subscription period.

## Ordering scheduled changes

Harborlight applies a scheduled downgrade and planned seat reduction at the
start of the next renewal period. If an Owner upgrades again before that date,
the newest confirmed plan selection replaces the scheduled downgrade. Changing
the billing contact or payment card does not change the billing anchor, cadence,
or the effective date of a scheduled plan change.

## What to check when dates look wrong

1. Confirm monthly versus annual cadence.
2. Check the billing anchor and billing timezone on the invoice.
3. Distinguish a regular renewal invoice from a prorated upgrade or seat invoice.
4. Compare the invoice issue date with the card statement posting date.
5. Contact Billing with the invoice ID if the displayed anchor is incorrect.
