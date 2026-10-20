-- question: Which advertising products have the most available inventory next month?
-- category: inventory
-- expected: Website Display Package 39 | Video Pre-Roll 30 | Daily Newsletter Sponsorship 20 | Podcast Host-Read Spot 12
-- why: Next month = October 2026 (reference date 2026-09-30). Available = inventory minus active
--      booked placements for that delivery month. Bookings are summed per product/month BEFORE the
--      join so inventory is never repeated; LEFT JOIN keeps products with no bookings.
SELECT p.product_name, i.total_placements - COALESCE(b.booked, 0) AS available_placements
FROM inventory i
JOIN products p ON p.product_id = i.product_id
LEFT JOIN (SELECT product_id, delivery_month, sum(placements) AS booked
           FROM bookings WHERE status = 'active'
           GROUP BY product_id, delivery_month) b
  ON b.product_id = i.product_id AND b.delivery_month = i.inventory_month
WHERE i.inventory_month = DATE '2026-10-01'
ORDER BY available_placements DESC;
