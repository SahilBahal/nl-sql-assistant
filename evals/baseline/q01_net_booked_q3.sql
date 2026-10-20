-- question: What was our net booked value in Q3 2026?
-- category: totals
-- expected: 52060.00
-- why: Net booked value = active line items (dictionary). "Booked in Q3" means
--      booking_date in Jul 1 to Sep 30, not delivery month. Single table, no joins,
--      so nothing can be double-counted.
SELECT sum(amount) AS net_booked_value
FROM bookings
WHERE status = 'active'
  AND booking_date BETWEEN DATE '2026-07-01' AND DATE '2026-09-30';