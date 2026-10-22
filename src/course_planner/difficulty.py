"""Difficulty score from 1 (easy) to 10 (hard), from a fixed weighted heuristic.

Per the proposal: credit hours 35%, number of graded assessments 35%, and
aggregated review sentiment 30%. A course with no reviews uses only the two
document-based factors, with their weights rescaled so the score still spans
1-10 (and the result is marked ``review_free``). Reviews are combined with a
trimmed mean so contradictory or extreme ratings are neither discarded nor
taken at face value.

The score is based on past student reviews and the requirement document. It is
not an official HKU rating.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from course_planner.models import Course

CREDIT_WEIGHT = 0.35
ASSESSMENT_WEIGHT = 0.35
SENTIMENT_WEIGHT = 0.30

MIN_SCORE = 1.0
MAX_SCORE = 10.0

# Values at (or above) which a factor counts as maximally demanding.
CREDITS_CAP = 12
ASSESSMENTS_CAP = 8

# Used when the document does not state credits or assessments, so the course
# still gets a score. Mid-range values; the result is flagged as incomplete.
DEFAULT_CREDITS = 6
DEFAULT_ASSESSMENTS = 4

TRIM_FRACTION = 0.2


@dataclass(frozen=True)
class DifficultyScore:
    """A 1-10 score plus everything needed to explain it."""

    score: float
    review_free: bool
    review_count: int
    # Each factor normalised to 0-1 (1 = most demanding); ``None`` if unused.
    credit_factor: float
    assessment_factor: float
    sentiment_factor: float | None
    # True when credits or assessments were missing and a default was used.
    used_defaults: bool = False

    @property
    def label(self) -> str:
        """Short text for the UI so status never relies on colour alone."""
        basis = "document only, no reviews" if self.review_free else "past student reviews"
        return f"{self.score:.1f}/10 (based on {basis})"


def trimmed_mean(values: Sequence[float], trim_fraction: float = TRIM_FRACTION) -> float:
    """Mean after dropping the lowest and highest ``trim_fraction`` of values.

    Fewer than ``1 / trim_fraction`` values means nothing is trimmed, so a tiny
    sample is never reduced to a single point.
    """
    if not values:
        raise ValueError("trimmed_mean needs at least one value")
    ordered = sorted(values)
    cut = math.floor(len(ordered) * trim_fraction)
    kept = ordered[cut : len(ordered) - cut]
    return sum(kept) / len(kept)


def difficulty_score(
    course: Course, review_sentiments: Sequence[float] = ()
) -> DifficultyScore:
    """Score one course.

    ``review_sentiments`` holds one value per review in [-1, 1], where -1 is
    very negative (reviewer found the course hard or unpleasant) and +1 is very
    positive. Values outside that range are clamped.
    """
    used_defaults = course.credits is None or course.assessments is None
    credit_factor = _normalise(
        course.credits if course.credits is not None else DEFAULT_CREDITS, CREDITS_CAP
    )
    assessment_factor = _normalise(
        course.assessments if course.assessments is not None else DEFAULT_ASSESSMENTS,
        ASSESSMENTS_CAP,
    )

    sentiments = [max(-1.0, min(1.0, s)) for s in review_sentiments if not math.isnan(s)]
    if sentiments:
        # Negative sentiment means harder, so flip it onto a 0-1 difficulty scale.
        sentiment_factor: float | None = (1 - trimmed_mean(sentiments)) / 2
        weighted = (
            CREDIT_WEIGHT * credit_factor
            + ASSESSMENT_WEIGHT * assessment_factor
            + SENTIMENT_WEIGHT * sentiment_factor
        )
    else:
        sentiment_factor = None
        document_weight = CREDIT_WEIGHT + ASSESSMENT_WEIGHT
        weighted = (
            CREDIT_WEIGHT * credit_factor + ASSESSMENT_WEIGHT * assessment_factor
        ) / document_weight

    return DifficultyScore(
        score=round(MIN_SCORE + (MAX_SCORE - MIN_SCORE) * weighted, 2),
        review_free=not sentiments,
        review_count=len(sentiments),
        credit_factor=credit_factor,
        assessment_factor=assessment_factor,
        sentiment_factor=sentiment_factor,
        used_defaults=used_defaults,
    )


def _normalise(value: float, cap: float) -> float:
    return max(0.0, min(1.0, value / cap))
