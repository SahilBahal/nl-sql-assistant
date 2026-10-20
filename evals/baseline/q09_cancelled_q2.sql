-- question: How much booked value was cancelled for deals booked in Q2 2026?
-- category: totals, filters
-- expected: 12500.00 (2 line items)
-- why: Cancelled lines are excluded from net booked value, so this is the inverse filter
--      (status = 'cancelled'). "Booked in Q2" = booking_date Apr 1 to Jun 30.
SELECT sum(amount) AS cancelled_value, count(*) AS cancelled_lines
FROM bookings
WHERE status = 'cancelled'
  AND booking_date BETWEEN DATE '2026-04-01' AND DATE '2026-06-30';
