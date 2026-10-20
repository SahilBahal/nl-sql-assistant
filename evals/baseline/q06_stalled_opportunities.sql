-- question: Which opportunities have had no activity for more than 30 days?
-- category: date filters
-- expected: Atlas Fitness - Jun 2026 (2026-07-22) | Summit Ridge Travel - Jun 2026 (2026-07-27)
-- why: Stalled = open stage AND last_activity_date more than 30 days before the reference date
--      2026-09-30 (dictionary). Closed deals are excluded even if old.
SELECT opportunity_name, stage, amount, last_activity_date
FROM opportunities
WHERE stage NOT IN ('closed_won', 'closed_lost')
  AND last_activity_date < DATE '2026-09-30' - 30
ORDER BY last_activity_date;
