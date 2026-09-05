---
document_id: KB-TEC-003
title: CSV export limits and troubleshooting
domain: technical
product: Harborlight Workspace
---

# CSV export limits

Harborlight Workspace creates CSV exports asynchronously so large requests do
not block normal workspace work. An export contains only records the requesting
user or API key is permitted to read at the moment the export is created.

## Limits by plan

| Plan | Rows per export | Export jobs per day |
|---|---:|---:|
| Starter | 25,000 | 10 |
| Growth | 100,000 | 50 |
| Scale | 500,000 | 200 |

Each export can include up to 50 columns. A filter that matches more rows than
the plan limit is rejected rather than silently truncated. Narrow the date
range, project scope, or status filter, then create separate exports.

## Export lifecycle

1. A user or API client requests an export.
2. Harborlight validates permissions, filters, plan limits, and daily quota.
3. The job enters `queued`, then `processing`, then `completed` or `failed`.
4. A completed export receives a signed download link that expires after 24
   hours.

Poll a job no more than once every 10 seconds. Repeated rapid polling consumes
API rate-limit capacity without making the export finish faster. Where enabled,
use an export-completed webhook instead.

## File rules

Exports use UTF-8 encoding, comma separators, a header row, and ISO-8601 dates
in UTC unless a report explicitly documents a workspace-timezone field. Text
values containing commas, quotes, or line breaks are quoted according to normal
CSV rules. Spreadsheet programs may reinterpret IDs or leading-zero values, so
import sensitive identifier columns as text.

## Common failures

### Too many rows

Reduce the query scope. For example, export one quarter at a time instead of an
entire multi-year workspace history. The response explains the applicable plan
limit and does not create a partial file.

### Download link expired

Create a new export. Download links cannot be extended because they are short-
lived security credentials.

### Export is stuck in processing

Wait at least 15 minutes for a large export, then check the status page for an
active incident. If no incident is listed, contact Support with the export job
ID, workspace, creation time, and `X-Request-ID` if the API was used.

### CSV opens with incorrect characters

Confirm that the receiving application imports UTF-8. Do not edit the file in a
spreadsheet and re-upload it as evidence, because that can alter dates and IDs.

## Billing relationship

Export limits are plan limits, not seat counts. Moving to a higher plan can
increase future export capacity immediately after an upgrade, while a scheduled
downgrade applies the lower limit only on its effective renewal date.
