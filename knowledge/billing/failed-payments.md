---
document_id: KB-BIL-002
title: Failed payments and collection retries
domain: billing
product: Harborlight Workspace
---

# Failed payments and collection retries

Harborlight Workspace attempts to collect card-backed invoices automatically.
A failed payment does not immediately disable a workspace. The invoice stays
`open` until its due date, then becomes `past_due` if a balance remains.

## Retry schedule

For an invoice issued to a saved card, Harborlight attempts payment on:

| Attempt | Timing | What happens |
|---|---|---|
| 1 | Invoice issue date | Initial charge attempt. |
| 2 | 3 days after issue | Retry if the first attempt failed. |
| 3 | 7 days after issue | Retry after a second failure. |
| 4 | 10 days after issue | Final automatic retry before the due date. |

The due date is always 14 calendar days after issue. Updating the payment method
triggers one immediate retry if the invoice is still open. It does not reset the
four-attempt schedule or create a duplicate invoice.

## Grace period and access

When the due date passes, the invoice becomes `past_due`. The workspace remains
available for a seven-day grace period. During that period, Owners and Billing
Admins see a payment banner and can update billing information. Existing users
can continue their normal work.

After the grace period, the workspace becomes billing-restricted: members can
sign in and export their own permitted data, but creating new work items,
inviting members, and changing workspace settings are disabled. API write
operations are also rejected. Read-only access is retained for 30 additional
days. Paying the overdue balance restores normal access automatically; no data
is deleted because of a single missed invoice.

## Typical failure reasons

- The card expired or was replaced.
- The bank declined a recurring or international charge.
- The card has insufficient funds or a spending limit.
- The billing postal code does not match the card issuer record.
- The payment method belongs to a cardholder who removed authorization.

Harborlight intentionally does not expose full processor decline details. The
workspace shows a safe reason such as “card declined” or “payment method needs
attention.”

## How an Owner or Billing Admin fixes it

1. Open **Workspace settings → Billing → Payment methods**.
2. Add a new card or update the existing card’s billing postal code.
3. Make the new method default.
4. Open the affected invoice and confirm that the immediate retry succeeded.
5. If payment still fails, ask the card issuer whether recurring online charges
   from Harborlight Software are allowed.

Only Owners and Billing Admins can change payment methods. An Admin can view the
workspace subscription but cannot update a card.

## Edge cases

If two cards are saved, Harborlight uses only the designated default card; it
never silently charges a secondary card. Bank-transfer customers do not receive
automatic card retries and should follow the payment instructions on the open
invoice. If a retry succeeds after a manual payment was started, the manual
payment is cancelled or returned rather than applied twice.
