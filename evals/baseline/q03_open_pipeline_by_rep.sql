-- question: How much open pipeline does each salesperson own?
-- category: joins, grouping
-- expected: Alex Rivera 43000.00 | Jordan Price 39000.00 | Maya Chen 10000.00
-- why: Open pipeline = opportunities not closed_won/closed_lost (dictionary). Ownership is
--      opportunities.owner_rep_id. Never joined to bookings, so deal amounts can't be repeated.
SELECT r.full_name, sum(o.amount) AS open_pipeline
FROM opportunities o
JOIN sales_reps r ON r.rep_id = o.owner_rep_id
WHERE o.stage NOT IN ('closed_won', 'closed_lost')
GROUP BY r.full_name
ORDER BY open_pipeline DESC;
