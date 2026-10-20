-- question: What is booked for Q3 2026 delivery, by product?
-- category: joins, grouping
-- expected: Daily Newsletter Sponsorship 29025.00 | Video Pre-Roll 14700.00 | Podcast Host-Read Spot 13500.00 | Website Display Package 9040.00
-- why: Same filter as q02 (delivery_month Jul-Sep, active), grouped by product. Rows add up to
--      q02's 66265.00, which is a built-in consistency check.
SELECT p.product_name, sum(b.amount) AS booked_value
FROM bookings b
JOIN products p ON p.product_id = b.product_id
WHERE b.status = 'active'
  AND b.delivery_month BETWEEN DATE '2026-07-01' AND DATE '2026-09-01'
GROUP BY p.product_name
ORDER BY booked_value DESC;
