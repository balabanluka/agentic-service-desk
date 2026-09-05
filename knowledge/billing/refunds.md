---
document_id: KB-BIL-003
title: Refunds, credits, and billing corrections
domain: billing
product: Harborlight Workspace
---

# Refunds, credits, and billing corrections

Harborlight Software reviews refund requests for charges that were processed in
error, duplicated, or caused by a documented service failure. A refund is not
the normal mechanism for changing plans or reducing seats; those changes follow
the subscription and seat policies.

## When a refund may apply

Billing can approve a full or partial refund when one of these situations is
verified:

- The same invoice was paid twice.
- A payment was captured after a cancellation that had already taken effect.
- Harborlight charged a documented configuration or processing error.
- A confirmed service incident made a paid feature materially unavailable for a
  significant part of the billing period.

Requests should be submitted within 30 calendar days of the payment date. The
30-day window lets Billing verify the payment reference while processor records
are readily available. It is not an automatic entitlement: the invoice and
workspace history are reviewed first.

## What does not normally receive a refund

- Unused time after a scheduled downgrade.
- Seat removals made during an active billing period.
- A renewal that was not cancelled before its renewal date.
- Charges caused by a workspace member being assigned a billable role.
- Fees charged by a customer’s bank or card issuer.

Downgrades and seat removals take effect at the next billing boundary, so they
avoid retroactive recalculation of completed invoices. See the plan and
seat-based charge policies for timing details.

## Refund versus account credit

A **refund** returns money to the original payment method. An **account credit**
reduces a future Harborlight invoice. Billing may offer a credit when the
original card is closed, when a bank transfer cannot be reversed, or when a
small adjustment is faster to apply to an upcoming invoice.

Credits are shown as a negative line item on a later invoice. They cannot be
cashed out, transferred to another workspace, or used to pay a separate
Harborlight customer account.

## Timing

After approval, card refunds are submitted within three business days. The card
issuer may take an additional 5–10 business days to show the credit. Bank
transfer corrections are handled case by case and can require confirmed account
details from the payer. A paid invoice remains `paid`; the refund is recorded
separately so both the original charge and correction remain auditable.

## What to send Billing

Include the workspace name, invoice ID, payment date, amount in dispute, and a
brief explanation. Screenshots may help, but redact card numbers and bank data.
Do not send passwords, API keys, or full payment-method details.

## Example

If invoice `inv_example_1042` was paid by card on 2 June and an identical
second charge appears on 3 June, Billing verifies both processor references. If
they represent a duplicate capture, Harborlight refunds the duplicate amount to
the same card. If the second entry is only a temporary authorization, no refund
is needed because the authorization expires without settling.
