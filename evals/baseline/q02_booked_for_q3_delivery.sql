-- question: How much is booked for Q3 2026 delivery?
-- category: date filters
-- expected: 66265.00
-- why: "For Q3 delivery" filters delivery_month (Jul, Aug, Sep 2026), not booking_date.
--      It's larger than q01 because Q2 deals delivered ads in Q3. Same metric, different date field.
SELECT sum(amount) AS booked_for_q3_delivery
FROM bookings
WHERE status = 'active'
  AND delivery_month BETWEEN DATE '2026-07-01' AND DATE '2026-09-01';