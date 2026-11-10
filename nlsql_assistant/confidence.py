"""Score how much to trust an answer, from evidence the app already has. The model is never asked to rate itself.

Every answer starts at 100 and loses points for each warning sign, and each deduction comes with a reason
so the user can see why the score is what it is.
"""
from dataclasses import dataclass, field

HIGH, MEDIUM = 80, 50  # score >= 80 is High, >= 50 is Medium, anything lower is Low


@dataclass
class Confidence:
    score: int = 100
    reasons: list = field(default_factory=list)

    @property
    def level(self):
        return "High" if self.score >= HIGH else "Medium" if self.score >= MEDIUM else "Low"

    def deduct(self, points, reason):
        self.score = max(0, self.score - points)
        self.reasons.append(f"-{points}: {reason}")


def score_confidence(interpretation, clarified, retried, semantic, rows=None, truncated=False):
    """Score one answer. Pass rows=None before the query runs, and the result rows after."""
    confidence = Confidence()

    if interpretation.needs_clarification:
        confidence.deduct(30, "the question is still ambiguous after clarification")
    elif clarified:
        confidence.deduct(5, "the question needed a clarification")
    if interpretation.metric == "other":
        confidence.deduct(20, "the question doesn't match a metric in the business dictionary")
    extra_assumptions = len(interpretation.assumptions) - 4
    if extra_assumptions > 0:
        confidence.deduct(min(10, 2 * extra_assumptions), f"{len(interpretation.assumptions)} assumptions were needed")

    if retried:
        confidence.deduct(15, "the first SQL failed the checks and had to be corrected")
    if semantic.issues:
        confidence.deduct(min(50, 25 * len(semantic.issues)),
                          f"{len(semantic.issues)} semantic warning(s) remain")

    if rows is not None:
        if not rows:
            confidence.deduct(30, "the query returned no rows, which may mean a wrong filter or date")
        elif len(rows) == 1 and all(value is None for value in rows[0]):
            confidence.deduct(30, "the query returned only an empty (NULL) value")
        if truncated:
            confidence.deduct(5, "the result was cut off at the row limit")

    return confidence
