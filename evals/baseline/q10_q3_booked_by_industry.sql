-- question: What was net booked value by client industry in Q3 2026?
-- category: joins
-- expected: Finance 26815.00 | Retail 25245.00
-- why: Industry lives on accounts, so the approved path is bookings -> opportunities -> accounts.
--      Each booking matches exactly one opportunity and one account, so nothing is repeated.
--      Rows add up to q01's 52060.00.
SELECT a.industry, sum(b.amount) AS net_booked_value
FROM bookings b
JOIN opportunities o ON o.opportunity_id = b.opportunity_id
JOIN accounts a ON a.account_id = o.account_id
WHERE b.status = 'active'
  AND b.booking_date BETWEEN DATE '2026-07-01' AND DATE '2026-09-30'
GROUP BY a.industry
ORDER BY net_booked_value DESC;
