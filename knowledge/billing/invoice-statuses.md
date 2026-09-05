---
document_id: KB-BIL-001
title: Invoice statuses in Harborlight Workspace
domain: billing
product: Harborlight Workspace
---

# Invoice statuses

Harborlight Workspace invoices show the state of a specific charge, not the
state of the whole subscription. A workspace can have an active subscription
while its newest invoice is still open, and it can have a past-due invoice while
the workspace remains usable during the payment grace period.

## Status definitions

| Status | Meaning | Customer action |
|---|---|---|
| `draft` | Harborlight is preparing the invoice; it is not payable yet. | None. Drafts are not normally visible in the workspace. |
| `open` | The invoice was issued and has an unpaid balance. | Review the amount and pay before the due date. |
| `paid` | The full balance was received or fully credited. | Keep the receipt for records. |
| `past_due` | The due date passed with a balance remaining. | Update payment details or pay immediately. |
| `void` | The invoice was cancelled before payment was completed. | Do not pay it; use any replacement invoice instead. |
| `uncollectible` | Collection attempts ended and the balance is no longer being pursued automatically. | Contact Billing if the invoice appears incorrect. |

An invoice never moves from `paid` back to `open`. If a settled charge needs to
be reversed, Harborlight issues a separate refund or credit record rather than
rewriting the paid invoice.

## Dates and balances

Every issued invoice includes an issue date, due date, currency, line items,
amount paid, and remaining balance. Standard invoices are due 14 calendar days
after issue. For example, an invoice issued on 4 May is due on 18 May at 23:59
in the workspace billing timezone. The billing timezone is set when the
workspace is created and is shown on the invoice PDF.

`Open` does not necessarily mean a payment card has not been tried. Card-backed
subscriptions begin automatic collection when an invoice is issued. The invoice
remains open until the payment succeeds or the due date passes. Manual-payment
workspaces remain open until the customer pays through the invoice link or bank
instructions.

## Common situations

### An invoice is open but the card is valid

Check whether the invoice was issued recently. A card payment can remain pending
for a short period. If it is still open after one business day, check the failed
payment details and confirm that the card supports online recurring charges.

### A paid invoice is missing from the list

Verify that the correct workspace is selected. Invoices belong to one workspace,
not to an individual member. Owners and Billing Admins can view invoices; Members
and Viewers cannot.

### A void invoice looks like a duplicate charge

Compare the invoice IDs. A void invoice produces no completed charge. A common
case is a seat change that creates a draft, then replaces it with a corrected
invoice after the seat count changes again.

## Troubleshooting checklist

1. Confirm the workspace name and invoice ID.
2. Compare the issue date, due date, currency, and remaining balance.
3. Check whether a replacement invoice references the void invoice.
4. For a paid invoice, compare the payment reference with the card or bank
   statement.
5. If the line items are unclear, contact Billing with the invoice ID; do not
   send card numbers or full bank-account details.
