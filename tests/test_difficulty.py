import pytest

from course_planner.difficulty import difficulty_score, trimmed_mean
from course_planner.models import Course


def test_trimmed_mean_small_sample_is_plain_mean():
    assert trimmed_mean([0.0, 1.0, 0.5]) == pytest.approx(0.5)


def test_trimmed_mean_drops_extremes():
    values = [-1.0, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 1.0]
    assert trimmed_mean(values) == pytest.approx(0.2)


def test_trimmed_mean_rejects_empty():
    with pytest.raises(ValueError):
        trimmed_mean([])


def test_minimum_course_scores_one():
    result = difficulty_score(Course("X", credits=0, assessments=0), [1.0, 1.0])
    assert result.score == 1.0


def test_maximum_course_scores_ten():
    result = difficulty_score(Course("X", credits=12, assessments=8), [-1.0, -1.0])
    assert result.score == 10.0


def test_weights_are_35_35_30():
    # Only the credit factor is maxed: 1 + 9 * 0.35.
    credits_only = difficulty_score(Course("X", credits=12, assessments=0), [1.0])
    assert credits_only.score == pytest.approx(1 + 9 * 0.35)
    assessments_only = difficulty_score(Course("X", credits=0, assessments=8), [1.0])
    assert assessments_only.score == pytest.approx(1 + 9 * 0.35)
    sentiment_only = difficulty_score(Course("X", credits=0, assessments=0), [-1.0])
    assert sentiment_only.score == pytest.approx(1 + 9 * 0.30)


def test_review_free_rescales_weights_to_full_range():
    low = difficulty_score(Course("X", credits=0, assessments=0))
    high = difficulty_score(Course("X", credits=12, assessments=8))
    assert (low.score, high.score) == (1.0, 10.0)
    assert low.review_free and high.review_free
    assert low.review_count == 0 and low.sentiment_factor is None
    assert "no reviews" in low.label


def test_reviews_move_the_score_in_the_expected_direction():
    course = Course("X", credits=6, assessments=4)
    hard = difficulty_score(course, [-0.8, -0.6, -0.9])
    easy = difficulty_score(course, [0.8, 0.6, 0.9])
    none = difficulty_score(course)
    assert easy.score < none.score < hard.score
    assert not hard.review_free and hard.review_count == 3
    assert "past student reviews" in hard.label


def test_outlier_review_has_limited_effect_with_trimming():
    course = Course("X", credits=6, assessments=4)
    consistent = [0.0] * 9
    with_outlier = [*consistent, -1.0]
    assert difficulty_score(course, with_outlier).score == difficulty_score(
        course, consistent
    ).score


def test_missing_document_fields_use_defaults_and_are_flagged():
    result = difficulty_score(Course("X"))
    assert result.used_defaults
    assert result.score == difficulty_score(Course("X", credits=6, assessments=4)).score
    assert not difficulty_score(Course("X", credits=6, assessments=4)).used_defaults


def test_out_of_range_inputs_are_clamped():
    result = difficulty_score(Course("X", credits=99, assessments=99), [-5.0, float("nan")])
    assert result.score == 10.0
    assert result.review_count == 1


@pytest.mark.parametrize("credits", range(0, 16, 3))
@pytest.mark.parametrize("assessments", range(0, 12, 3))
@pytest.mark.parametrize("sentiments", [[], [-1.0], [0.0, 0.3], [1.0]])
def test_score_always_within_one_to_ten(credits, assessments, sentiments):
    score = difficulty_score(Course("X", credits=credits, assessments=assessments), sentiments)
    assert 1.0 <= score.score <= 10.0
