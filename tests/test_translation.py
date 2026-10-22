import csv
import sys
import types

import pytest

from course_planner.language import chinese_share, detect_language
from course_planner.models import Review
from course_planner.translation import (
    CachedTranslator,
    MarianTranslator,
    TranslationUnavailableError,
    export_review_sample,
    main,
    split_for_translation,
    translate_reviews,
)

# ------------------------------------------------------------------ language


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("This course has too many assignments.", "en"),
        ("這門課功課很多，但老師很好", "zh"),
        ("这门课作业太多了", "zh"),
        ("呢個 course 好 hard", "zh"),  # Cantonese mixed with English
        ("Prof. 陳 is very helpful and the exam was fair and easy to prepare", "en"),
        ("COMP2113 is fun!!! 123", "en"),
        ("", "en"),
        ("😀 123", "en"),
    ],
)
def test_detect_language(text, expected):
    assert detect_language(text) == expected


def test_chinese_share_ignores_digits_and_punctuation():
    assert chinese_share("123 ... !!") == 0.0
    assert chinese_share("好好abcd") == pytest.approx(1 / 3)


# ------------------------------------------------------------------ chunking


def test_short_text_is_one_chunk():
    assert split_for_translation("很難。", 200) == ["很難。"]


def test_splits_on_sentence_ends_and_keeps_chunks_under_limit():
    text = "第一句話。第二句話。第三句話。第四句話。"
    chunks = split_for_translation(text, max_chars=10)
    assert all(len(c) <= 10 for c in chunks)
    assert "".join(chunks) == text


def test_overlong_sentence_is_cut_not_dropped():
    text = "字" * 25
    chunks = split_for_translation(text, max_chars=10)
    assert [len(c) for c in chunks] == [10, 10, 5]
    assert "".join(chunks) == text


def test_blank_text_gives_no_chunks():
    assert split_for_translation("  \n ") == []


# ------------------------------------------------------------------ fake translators


class Fake:
    def __init__(self):
        self.calls = []

    def translate(self, texts):
        self.calls.append(list(texts))
        return [f"EN:{t}" for t in texts]


class Broken:
    def translate(self, texts):
        raise RuntimeError("boom")


class Flaky:
    """Fails whenever a batch contains the word 坏."""

    def translate(self, texts):
        if any("坏" in t for t in texts):
            raise RuntimeError("bad input")
        return [f"EN:{t}" for t in texts]


class Missing:
    def translate(self, texts):
        raise TranslationUnavailableError("model missing. Download it.")


def review(text, code="COMP1117", rating=None):
    return Review(code, text, rating)


# ------------------------------------------------------------------ translate_reviews


def test_english_passes_through_and_chinese_is_translated_with_original_kept():
    fake = Fake()
    result = translate_reviews([review("Easy course."), review("功課很多")], fake)
    english, chinese = result.reviews
    assert (english.language, english.translation_status, english.translation) == (
        "en",
        "not_needed",
        "Easy course.",
    )
    assert (chinese.language, chinese.translation_status) == ("zh", "translated")
    assert chinese.text == "功課很多" and chinese.translation == "EN:功課很多"
    assert chinese.english_text == "EN:功課很多"
    assert fake.calls == [["功課很多"]]  # English never reaches the translator
    assert result.warning is None and result.translated_count == 1


def test_no_chinese_means_translator_is_never_called():
    fake = Fake()
    result = translate_reviews([review("fine"), review("ok")], fake)
    assert fake.calls == [] and result.translated_count == 0 and result.failed_count == 0


def test_rating_and_course_code_survive_translation():
    result = translate_reviews([review("很難", "COMP2119", 2.5)], Fake())
    assert result.reviews[0].course_code == "COMP2119" and result.reviews[0].rating == 2.5


def test_one_bad_review_does_not_sink_the_rest():
    result = translate_reviews([review("很好"), review("很坏"), review("不錯")], Flaky())
    statuses = [r.translation_status for r in result.reviews]
    assert statuses == ["translated", "failed", "translated"]
    assert result.failed_count == 1 and len(result.failures) == 1
    assert result.reviews[1].english_text is None
    assert "1 Chinese review(s) could not be translated" in result.warning


def test_total_failure_marks_all_chinese_reviews_failed():
    result = translate_reviews([review("很好"), review("fine")], Broken())
    assert [r.translation_status for r in result.reviews] == ["failed", "not_needed"]
    assert result.reviews[1].english_text == "fine"


def test_unavailable_model_is_reported_in_plain_words():
    result = translate_reviews([review("很好"), review("不錯")], Missing())
    assert result.failed_count == 2 and result.translated_count == 0
    assert "left out of the difficulty score" in result.warning
    assert "Download it." in result.warning


def test_empty_translation_counts_as_failure():
    class Empty:
        def translate(self, texts):
            return ["" for _ in texts]

    result = translate_reviews([review("很好")], Empty())
    assert result.reviews[0].translation_status == "failed"


# ------------------------------------------------------------------ cache


def test_cached_translator_translates_each_text_once():
    fake = Fake()
    cached = CachedTranslator(fake)
    assert cached.translate(["很好", "不錯", "很好"]) == ["EN:很好", "EN:不錯", "EN:很好"]
    assert cached.translate(["很好", "新的"]) == ["EN:很好", "EN:新的"]
    assert fake.calls == [["很好", "不錯"], ["新的"]]


def test_cached_translator_uses_supplied_mapping():
    store = {"很好": "good"}
    cached = CachedTranslator(Fake(), store)
    assert cached.translate(["很好"]) == ["good"]
    cached.translate(["不錯"])
    assert store["不錯"] == "EN:不錯"


# ------------------------------------------------------------------ Marian backend


def test_marian_without_libraries_raises_helpful_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "transformers", None)
    with pytest.raises(TranslationUnavailableError, match="translation extras"):
        MarianTranslator().translate(["很好"])


@pytest.fixture
def fake_transformers(monkeypatch):
    """A stand-in for transformers that echoes text, so chunking/batching can be tested."""
    seen = {"batches": [], "kwargs": []}

    class Tokenizer:
        @classmethod
        def from_pretrained(cls, name, **kwargs):
            seen["kwargs"].append(kwargs)
            return cls()

        def __call__(self, batch, **kwargs):
            seen["batches"].append(list(batch))
            return {"batch": list(batch)}

        def batch_decode(self, output, skip_special_tokens):
            return [f"EN({t})" for t in output]

    class Model:
        @classmethod
        def from_pretrained(cls, name, **kwargs):
            return cls()

        def generate(self, batch, max_new_tokens):
            return batch

    module = types.SimpleNamespace(MarianTokenizer=Tokenizer, MarianMTModel=Model)
    monkeypatch.setitem(sys.modules, "transformers", module)
    return seen


def test_marian_chunks_batches_and_rejoins(fake_transformers):
    translator = MarianTranslator(batch_size=2, max_chars=6)
    result = translator.translate(["一二三。四五六。", "短"])
    assert result == ["EN(一二三。) EN(四五六。)", "EN(短)"]
    assert [len(b) for b in fake_transformers["batches"]] == [2, 1]
    assert fake_transformers["kwargs"][0] == {"local_files_only": True}


def test_marian_empty_input_does_not_load_the_model(monkeypatch):
    monkeypatch.setitem(sys.modules, "transformers", None)
    assert MarianTranslator().translate([]) == []


def test_marian_missing_model_files_points_to_download(monkeypatch):
    class Tokenizer:
        @classmethod
        def from_pretrained(cls, name, **kwargs):
            raise OSError("not found")

    module = types.SimpleNamespace(MarianTokenizer=Tokenizer, MarianMTModel=Tokenizer)
    monkeypatch.setitem(sys.modules, "transformers", module)
    with pytest.raises(TranslationUnavailableError, match="translation download"):
        MarianTranslator().translate(["很好"])
    with pytest.raises(TranslationUnavailableError, match="internet connection"):
        MarianTranslator(local_files_only=False).translate(["很好"])


# ------------------------------------------------------------------ manual check sample


def test_export_review_sample_writes_blank_columns_for_the_checker(tmp_path):
    reviews = translate_reviews(
        [review(f"很好{i}", "COMP1117") for i in range(5)] + [review("fine")], Fake()
    ).reviews
    path = tmp_path / "sample.csv"
    assert export_review_sample(reviews, path, n=3, seed=1) == 3
    with open(path, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 3
    assert set(rows[0]) == {"course_code", "original", "machine_translation", "adequate", "notes"}
    assert all(r["original"].startswith("很好") and r["adequate"] == "" for r in rows)
    assert export_review_sample(reviews, path, n=3, seed=1) == 3  # reproducible


def test_export_sample_smaller_than_requested(tmp_path):
    reviews = translate_reviews([review("很好")], Fake()).reviews
    assert export_review_sample(reviews, tmp_path / "s.csv", n=30) == 1


# ------------------------------------------------------------------ CLI


def test_cli_usage_and_missing_library(monkeypatch, capsys):
    assert main([]) == 2
    monkeypatch.setitem(sys.modules, "transformers", None)
    assert main(["translate", "很好"]) == 1
    assert "translation extras" in capsys.readouterr().out
