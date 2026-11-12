"""Load course reviews from the local dataset for the difficulty score.

The app never fetches reviews from the network and never needs an RIC or HKU
password: the team collects reviews once into a CSV next to the app (see the
README's dataset-preparation section) and ``load_dataset`` reads that file.

Dataset columns: ``course_code``, ``text``, ``rating`` and an optional
``translation`` for reviews that are not already in English. ``rating`` uses
the dataset's own scale, mapped to a -1..1 sentiment by
``rating_to_sentiment``. Reviews the app cannot use (Chinese reviews without a
translation, reviews without a rating on the 1-5 scale) are counted in ``ReviewDataset.excluded``
so the app can say so rather than silently dropping them.
"""

from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from course_planner.language import detect_language
from course_planner.models import Review

REVIEWS_ENV_VAR = "COURSE_PLANNER_REVIEWS"
DEFAULT_REVIEWS = Path(__file__).resolve().parents[2] / "data" / "reviews" / "sample_reviews.csv"

# The sample dataset rates courses from 1 (worst) to 5 (best).
RATING_MIN = 1.0
RATING_MAX = 5.0


def default_reviews_path() -> Path:
    return Path(os.environ.get(REVIEWS_ENV_VAR, DEFAULT_REVIEWS))


@dataclass(frozen=True)
class ReviewDataset:
    """Reviews loaded from the local dataset, plus what they contribute to scores.

    ``sentiments`` maps course code to one value in [-1, 1] per usable review
    (-1 = very negative, +1 = very positive). ``excluded`` counts reviews left
    out of the score: Chinese reviews without a translation and reviews without
    a usable 1-5 rating. The app is expected to tell the student about these.
    """

    reviews: list[Review] = field(default_factory=list)
    sentiments: dict[str, list[float]] = field(default_factory=dict)
    excluded: int = 0


def is_usable_rating(rating: float | None) -> bool:
    """A rating counts only if it is on the dataset's 1-5 scale.

    A rating of 0, or 7 on a 1-10 scale, is a different scale or a missing value. Clamping it
    would silently turn it into the hardest or easiest review, so it is left out and counted
    in ``ReviewDataset.excluded`` instead.
    """
    return rating is not None and RATING_MIN <= rating <= RATING_MAX


def rating_to_sentiment(rating: float) -> float:
    """Map a dataset rating onto -1 (very negative) to +1 (very positive).

    The rating scale is the dataset's own; the sample dataset uses 1-5.
    Values outside that range are clamped so an unexpected scale cannot
    blow up the score.
    """
    clamped = max(RATING_MIN, min(RATING_MAX, rating))
    return (clamped - (RATING_MIN + RATING_MAX) / 2) / ((RATING_MAX - RATING_MIN) / 2)


def load_dataset(path: Path | str | None = None) -> ReviewDataset:
    """Read the review CSV; a missing file gives an empty dataset, not an error.

    That way the app still works (and scores from the requirement document
    only) when no dataset has been prepared yet.
    """
    reviews_path = Path(path) if path is not None else default_reviews_path()
    if not reviews_path.exists():
        return ReviewDataset()

    reviews: list[Review] = []
    with open(reviews_path, newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            code = (row.get("course_code") or "").strip().upper()
            text = (row.get("text") or "").strip()
            if not code or not text:
                continue
            language = detect_language(text)
            supplied = (row.get("translation") or "").strip()
            if language == "en":
                translation, status = text, "not_needed"
            else:
                translation, status = (supplied, "translated") if supplied else (None, "failed")
            reviews.append(
                Review(
                    course_code=code,
                    text=text,
                    rating=_rating_or_none(row.get("rating")),
                    translation=translation,
                    language=language,
                    translation_status=status,
                )
            )

    sentiments: dict[str, list[float]] = {}
    excluded = 0
    for review in reviews:
        # The app never translates anything itself (README): Chinese reviews
        # without a prepared translation are left out of the score.
        if review.translation_status == "failed" or not is_usable_rating(review.rating):
            excluded += 1
            continue
        sentiments.setdefault(review.course_code, []).append(rating_to_sentiment(review.rating))
    return ReviewDataset(reviews, sentiments, excluded)


def review_rows(reviews: list[Review]) -> list[dict[str, str]]:
    """Table rows for showing the reviews behind a score, original text first.

    Every review is listed, including ones left out of the score, so a number
    can always be traced back to its source (proposal, section 5).
    """
    rows = []
    for review in reviews:
        used = review.translation_status != "failed" and is_usable_rating(review.rating)
        if review.translation_status == "failed":
            reason = "No — not translated"
        elif review.rating is None:
            reason = "No — no rating"
        elif not is_usable_rating(review.rating):
            reason = "No — rating outside 1-5"
        else:
            reason = "Yes"
        english = review.english_text if review.english_text != review.text else ""
        rows.append(
            {
                "Rating (1-5)": f"{review.rating:g}" if review.rating is not None else "—",
                "Original text": review.text,
                "English translation": english or "",
                "Used in score": ("✅ " if used else "⚠️ ") + reason,
            }
        )
    return rows


def _rating_or_none(value: str | None) -> float | None:
    match = re.search(r"\d+(?:\.\d+)?", value or "")
    return float(match.group()) if match else None
