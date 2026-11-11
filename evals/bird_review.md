# BIRD Mini-Dev (PostgreSQL): review of every miss

Run: 150 questions, stratified by difficulty (seed 42), Claude Opus 5.5 through the Anthropic API.
132 questions were answered; 18 were not run because the API account hit its monthly spending limit.
Official execution accuracy on the answered questions: **110/132 = 83.3%**. No generated query was blocked by
the validator, and only 1 needed a retry.

Each of the 22 misses was checked by hand against BIRD's reference ("gold") query and both result sets
(the side-by-side comparison of queries and results). This review is our own judgement, not an official re-grade.

| Verdict | Count | Question ids |
|---|---|---|
| Claude's answer is right; the reference query is wrong or contradicts BIRD's own hint | 14 | 1252, 1256, 672, 1399, 682, 1029, 1427, 847, 967, 879, 694, 1275, 1243, 234 |
| Tie: several answers are equally correct and the reference picks one arbitrarily | 2 | 1028, 736 |
| Debatable: the question can reasonably be read either way | 5 | 27, 94, 1179, 41, 28 |
| Real mistake by Claude | 1 | 1524 |

Details:
- **Counts rows instead of patients/users** (reference counts duplicate join rows): 1252, 1256, 672.
- **Reference contradicts the hint**: 1275 (uses 'negative'/'0' instead of the hinted '-'/'+-'), 1243 (COUNT where the hint says SUM), 682 (filters on the user's creation date and returns the user id instead of the post id), 234 (missing brackets around OR and the wrong atom ids).
- **Reference is malformed or answers a different question**: 1399 (14 rows of YES/NULL for a yes/no question), 1029 (sorts ascending for "highest"), 847 and 879 (pick a NULL lap time / sort speeds as text), 694 (shows the post owner, not the commenter, and orders by account age).
- **Reference returns fewer or extra columns than asked**: 1427 (adds the event type), 967 (drops the driver codes the question asks for).
- **Ties**: 1028 (identical logic; two teams tie, LIMIT 1 picks one), 736 (three heroes share the lowest intelligence; Claude lists all three).
- **Debatable**: 27 (inner vs left join for schools without scores), 41 (whether schools with no reading score can rank top 5), 28 (DOC code vs DOC type text), 1179 (which antibody columns), 94 (which salary the gap is measured from).
- **Real mistake**: 1524 compared the price column to the number 548.4 and matched no rows, most likely because of floating-point rounding; the reference compares it to the text '548.4', which Postgres converts to the column's own type.

Takeaway: the 83.3% official score understates accuracy. Excluding questions where the reference itself is wrong or
arbitrary, Claude had **1 clear error** and 5 judgement calls. BIRD's reference answers are known to contain errors;
the BIRD team released corrections in October 2026, and the copy used here (files dated June 2024) predates them.

BIRD Mini-Dev is licensed CC BY-SA 4.0 (https://github.com/bird-bench/mini_dev).
