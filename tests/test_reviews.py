from pathlib import Path

from course_planner.reviews import load_dataset, rating_to_sentiment

SAMPLE = Path(__file__).parent.parent / "data" / "reviews" / "sample_reviews.csv"

SAMPLE_COURSES = {
    "COMP1117", "COMP2113", "COMP2119", "COMP3230", "COMP3314", "MATH1013", "STAT2601",
}


def test_rating_to_sentiment_maps_the_scale_and_clamps():
    assert rating_to_sentiment(1) == -1.0
    assert rating_to_sentiment(3) == 0.0
    assert rating_to_sentiment(5) == 1.0
    assert rating_to_sentiment(0) == -1.0
    assert rating_to_sentiment(99) == 1.0


def test_missing_dataset_gives_an_empty_result(tmp_path):
    dataset = load_dataset(tmp_path / "missing.csv")
    assert dataset.reviews == []
    assert dataset.sentiments == {}
    assert dataset.excluded == 0


def test_sample_dataset_loads_with_sentiments_for_every_sample_course():
    dataset = load_dataset(SAMPLE)
    assert len(dataset.reviews) >= 20
    assert set(dataset.sentiments) == SAMPLE_COURSES
    assert all(-1.0 <= s <= 1.0 for values in dataset.sentiments.values() for s in values)
    assert dataset.excluded == 0


def test_translated_chinese_review_contributes_its_rating(tmp_path):
    path = tmp_path / "reviews.csv"
    path.write_text(
        "course_code,text,rating,translation\n"
        "COMP3230,功課好多,1,Lots of homework\n",
        encoding="utf-8",
    )
    dataset = load_dataset(path)
    assert dataset.sentiments == {"COMP3230": [-1.0]}
    review = dataset.reviews[0]
    assert review.language == "zh"
    assert review.translation_status == "translated"
    assert review.english_text == "Lots of homework"


def test_untranslated_chinese_review_is_left_out_and_counted(tmp_path):
    path = tmp_path / "reviews.csv"
    path.write_text(
        "course_code,text,rating,translation\n"
        "COMP1117,Good course,5,\n"
        "COMP1117,功課好多,1,\n",
        encoding="utf-8",
    )
    dataset = load_dataset(path)
    assert dataset.sentiments == {"COMP1117": [1.0]}
    assert dataset.excluded == 1


def test_review_without_a_rating_is_left_out_and_counted(tmp_path):
    path = tmp_path / "reviews.csv"
    path.write_text(
        "course_code,text,rating\n"
        "COMP1117,No rating given here,\n",
        encoding="utf-8",
    )
    dataset = load_dataset(path)
    assert dataset.sentiments == {}
    assert dataset.excluded == 1


def test_rows_without_a_code_are_skipped(tmp_path):
    path = tmp_path / "reviews.csv"
    path.write_text(
        "course_code,text,rating\n"
        ",orphan row,3\n"
        "COMP1117,Good course,5\n",
        encoding="utf-8",
    )
    assert len(load_dataset(path).reviews) == 1


def test_review_rows_keep_original_text_and_say_what_was_used():
    from course_planner.models import Review
    from course_planner.reviews import review_rows

    rows = review_rows(
        [
            Review("A1", "Fair exams", 4, "Fair exams", "en", "not_needed"),
            Review("A1", "功課很多", 2, "Lots of homework", "zh", "translated"),
            Review("A1", "太難了", 1, None, "zh", "failed"),
            Review("A1", "Fine", None, "Fine", "en", "not_needed"),
        ]
    )
    assert rows[0]["English translation"] == "" and rows[0]["Used in score"].endswith("Yes")
    assert rows[1]["Original text"] == "功課很多"
    assert rows[1]["English translation"] == "Lots of homework"
    assert "not translated" in rows[2]["Used in score"]
    assert "no rating" in rows[3]["Used in score"] and rows[3]["Rating (1-5)"] == "—"
