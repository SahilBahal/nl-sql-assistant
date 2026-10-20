-- question: Which clients spent less this quarter than last quarter?
-- category: period comparisons
-- expected: Fernwood Home -2760.00 | Bluepeak Financial -1625.00 | Northwind Outfitters -420.00
-- why: Reference date 2026-09-30, so this quarter = Q3, last = Q2 (both complete).
--      "Spent" = active bookings by booking_date. A quarter with no bookings counts as 0,
--      so Fernwood (Q2 only) is included. Client reached via bookings -> opportunities -> accounts.
WITH q AS (
  SELECT o.account_id,
         sum(b.amount) FILTER (WHERE b.booking_date BETWEEN DATE '2026-04-01' AND DATE '2026-06-30') AS q2,
         sum(b.amount) FILTER (WHERE b.booking_date BETWEEN DATE '2026-07-01' AND DATE '2026-09-30') AS q3
  FROM bookings b
  JOIN opportunities o ON o.opportunity_id = b.opportunity_id
  WHERE b.status = 'active'
  GROUP BY o.account_id
)
SELECT a.account_name, COALESCE(q.q2, 0) AS last_quarter, COALESCE(q.q3, 0) AS this_quarter,
       COALESCE(q.q3, 0) - COALESCE(q.q2, 0) AS change
FROM q
JOIN accounts a ON a.account_id = q.account_id
WHERE COALESCE(q.q3, 0) < COALESCE(q.q2, 0)
ORDER BY change;
