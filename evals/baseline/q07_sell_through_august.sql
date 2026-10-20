-- question: What was the sell-through rate by product in August 2026?
-- category: inventory, ratios
-- expected: Video Pre-Roll 36.7 | Podcast Host-Read Spot 25.0 | Daily Newsletter Sponsorship 20.0 | Website Display Package 10.0
-- why: Sell-through = active booked placements / total inventory, as a percent to 1 decimal.
--      Uses delivery month. NULLIF guards against zero inventory. Bookings summed before the join.
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
