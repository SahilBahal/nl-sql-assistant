# Business Dictionary

Definitions the assistant must follow. Each metric names its source table, date field, filters, unit, and approved joins.

## Dataset conventions
- **Reference date:** 2026-09-30 is "today". This quarter = Q3 2026 (Jul 1 to Sep 30), last quarter = Q2 2026 (Apr 1 to Jun 30), next month = October 2026.
- **Quarters** are calendar quarters. Q3 is complete as of the reference date, so Q2 vs Q3 is a full-period comparison. If a question compares a partial period, ask whether it means full period or period-to-date.
- **Currency:** USD, two decimals. **Placements:** a count of ad slots.
- **Months** are stored as the first day of the month (2026-10-01 = October 2026).
- **Booking date vs. delivery month:** "What did we book in Q3?" filters `bookings.booking_date`. "What is booked for Q3 delivery?" filters `bookings.delivery_month`. If a question doesn't say which, ask.
- **Scope:** values are booked advertising value, not recognized accounting revenue.

## Approved joins
| From | To | On |
|---|---|---|
| accounts | sales_reps | accounts.owner_rep_id = sales_reps.rep_id |
| opportunities | accounts | opportunities.account_id = accounts.account_id |
| opportunities | sales_reps | opportunities.owner_rep_id = sales_reps.rep_id |
| bookings | opportunities | bookings.opportunity_id = opportunities.opportunity_id |
| bookings (summed per product and month) | inventory | product_id and delivery_month = inventory_month |

**Double-counting rules**
- Never sum `opportunities.amount` after joining to `bookings`. One deal has many line items.
- Never sum `inventory.total_placements` after joining to unsummed `bookings`. Sum bookings per product and month first.
- A booking's client is found through `bookings -> opportunities -> accounts`.
- "A salesperson's pipeline" uses `opportunities.owner_rep_id`, not the account owner.

## Metrics

### Net booked value
- **Definition:** sum of active booking line-item amounts.
- **Source:** `bookings`
- **Date field:** `booking_date` for "booked in"; `delivery_month` for "booked for delivery in". Ask if unclear.
- **Filters:** `status = 'active'` (cancelled lines excluded).
- **Unit:** USD
- **Joins:** to `opportunities` and then `accounts` for client breakdowns.
- **Reference SQL (booked in Q3):**
  `SELECT sum(amount) FROM bookings WHERE status = 'active' AND booking_date BETWEEN '2026-07-01' AND '2026-09-30';`

### Open pipeline
- **Definition:** sum of opportunity amounts that are not closed.
- **Source:** `opportunities`
- **Date field:** none by default (current state as of the reference date).
- **Filters:** `stage NOT IN ('closed_won', 'closed_lost')`
- **Unit:** USD
- **Joins:** to `sales_reps` on `owner_rep_id` for "per salesperson". Never join to `bookings`.
- **Reference SQL (per salesperson):**
  `SELECT r.full_name, sum(o.amount) FROM opportunities o JOIN sales_reps r ON r.rep_id = o.owner_rep_id WHERE o.stage NOT IN ('closed_won', 'closed_lost') GROUP BY r.full_name;`



### Available placements
- **Definition:** inventory for a product and month, minus the active placements booked for that product and month.
- **Source:** `inventory`, plus `bookings` summed per product and month.
- **Date field:** `inventory.inventory_month` matched to `bookings.delivery_month` (when the ad runs, not when it was sold).
- **Filters:** `bookings.status = 'active'`. Cancelled lines free up their inventory.
- **Unit:** placements (count of ad slots).
- **Joins:** sum bookings per (product_id, delivery_month) first, then LEFT JOIN to `inventory` so months with no bookings still show full availability.
- **Reference SQL (next month = October 2026):**
```sql
SELECT p.product_name, i.total_placements, COALESCE(b.booked, 0) AS booked,
       i.total_placements - COALESCE(b.booked, 0) AS available
FROM inventory i
JOIN products p ON p.product_id = i.product_id
LEFT JOIN (SELECT product_id, delivery_month, sum(placements) AS booked
           FROM bookings WHERE status = 'active'
           GROUP BY product_id, delivery_month) b
  ON b.product_id = i.product_id AND b.delivery_month = i.inventory_month
WHERE i.inventory_month = DATE '2026-10-01'
ORDER BY available DESC;
```

### Sell-through rate
- **Definition:** active booked placements divided by total inventory, for the same product and month.
- **Source:** `inventory`, plus `bookings` summed per product and month (same join as available placements).
- **Date field:** `inventory_month` / `delivery_month`.
- **Filters:** `bookings.status = 'active'`.
- **Unit:** percent, rounded to 1 decimal (36.7 means 36.7%).
- **Edge case:** if inventory is 0, the rate is NULL (shown as n/a), never a divide-by-zero error.
- **Reference SQL (August 2026):**
```sql
SELECT p.product_name,
       round(100.0 * COALESCE(b.booked, 0) / NULLIF(i.total_placements, 0), 1) AS sell_through_pct
FROM inventory i
JOIN products p ON p.product_id = i.product_id
LEFT JOIN (SELECT product_id, delivery_month, sum(placements) AS booked
           FROM bookings WHERE status = 'active'
           GROUP BY product_id, delivery_month) b
  ON b.product_id = i.product_id AND b.delivery_month = i.inventory_month
WHERE i.inventory_month = DATE '2026-08-01'
ORDER BY sell_through_pct DESC;
```

### Stalled opportunity
- **Definition:** an open opportunity with no recorded activity for more than 30 days as of the reference date.
- **Source:** `opportunities`
- **Date field:** `last_activity_date`, compared with the reference date 2026-09-30.
- **Filters:** `stage NOT IN ('closed_won', 'closed_lost')` AND `last_activity_date < DATE '2026-09-30' - 30`.
- **Unit:** a list of deals ("which deals are stalled?") or a count ("how many?").
- **Reference SQL:**
```sql
SELECT opportunity_id, opportunity_name, stage, amount, last_activity_date
FROM opportunities
WHERE stage NOT IN ('closed_won', 'closed_lost')
  AND last_activity_date < DATE '2026-09-30' - 30
ORDER BY last_activity_date;
```

### Client spending change
- **Definition:** an account's net booked value in the later period minus its net booked value in the earlier period. Both periods must be stated explicitly. "This quarter vs. last quarter" means Q3 2026 vs. Q2 2026.
- **Source:** `bookings`
- **Date field:** `booking_date` ("spent" means booked in that period).
- **Filters:** `status = 'active'`.
- **Unit:** USD (negative = spent less).
- **Joins:** bookings -> opportunities -> accounts.
- **Edge case:** a period with no bookings counts as $0, so a client who stopped buying shows as a full decrease. Accounts with no bookings in either period are not listed.
- **Reference SQL (Q3 vs. Q2 2026):**
```sql
WITH q AS (
  SELECT o.account_id,
         sum(b.amount) FILTER (WHERE b.booking_date BETWEEN '2026-04-01' AND '2026-06-30') AS q2,
         sum(b.amount) FILTER (WHERE b.booking_date BETWEEN '2026-07-01' AND '2026-09-30') AS q3
  FROM bookings b
  JOIN opportunities o ON o.opportunity_id = b.opportunity_id
  WHERE b.status = 'active'
  GROUP BY o.account_id
)
SELECT a.account_name, COALESCE(q.q2, 0) AS q2_booked, COALESCE(q.q3, 0) AS q3_booked,
       COALESCE(q.q3, 0) - COALESCE(q.q2, 0) AS change
FROM q
JOIN accounts a ON a.account_id = q.account_id
ORDER BY change;
```