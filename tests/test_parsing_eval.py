import json
from pathlib import Path

import pytest

from course_planner.models import Course, ParseResult
from course_planner.parser import parse_document
from course_planner.parsing_eval import (
    AcceptanceReport,
    CourseLabel,
    evaluate_folders,
    find_document,
    load_labels,
    main,
    score_document,
)
from pdfutil import make_pdf

ROOT = Path(__file__).parent
LABELS = ROOT / "fixtures" / "labels"
DOCUMENT_DIRS = [ROOT / "fixtures" / "requirements", ROOT / "fixtures" / "messy"]
SAMPLES = ROOT.parent / "data" / "samples"


def label(*groups: tuple[str, ...], credits: int = 6, assessments: int = 3) -> CourseLabel:
    return CourseLabel(credits, assessments, frozenset(frozenset(g) for g in groups))


def test_labelled_documents_meet_the_proposal_bar():
    report = evaluate_folders(LABELS, [*DOCUMENT_DIRS, SAMPLES])
    assert len(report.documents) == 8
    assert report.passed, report.report()


def test_every_labelled_document_is_parsed_exactly():
    for doc in evaluate_folders(LABELS, [*DOCUMENT_DIRS, SAMPLES]).documents:
        assert not doc.missing_courses and not doc.extra_courses, doc.name
        assert not doc.missing_links and not doc.extra_links, doc.name
        assert doc.credits_correct == doc.credits_checked, doc.name
        assert doc.assessments_correct == doc.assessments_checked, doc.name


def test_pdf_versions_of_the_text_documents_meet_the_bar():
    """The same documents, but through the real PDF text-extraction path."""
    scores = []
    for label_path in sorted(LABELS.glob("*.json")):
        source = find_document(label_path.stem, [*DOCUMENT_DIRS, SAMPLES])
        assert source is not None
        if source.suffix != ".txt":
            continue
        pdf = make_pdf(source.read_text(encoding="utf-8"))
        scores.append(
            score_document(
                f"{source.stem}.pdf",
                parse_document(pdf, f"{source.stem}.pdf"),
                load_labels(label_path),
            )
        )
    assert len(scores) == 7
    report = AcceptanceReport(tuple(scores))
    assert report.passed, report.report()


def test_scoring_counts_a_half_right_or_group_as_wrong():
    labels = {"A1": label(), "B1": label(("A1",), ("C1", "D1"))}
    parsed = ParseResult(
        [
            Course("A1", credits=6, assessments=3),
            Course("B1", credits=6, assessments=3, prerequisites=(("A1",), ("C1",))),
            Course("Z9", credits=6, assessments=3),
        ]
    )
    score = score_document("doc", parsed, labels)
    assert score.missing_courses == [] and score.extra_courses == ["Z9"]
    assert score.missing_links == [("B1", frozenset({"C1", "D1"}))]
    assert score.extra_links == [("B1", frozenset({"C1"}))]

    report = AcceptanceReport((score,))
    assert report.course_recall == 1.0
    assert report.course_precision == pytest.approx(2 / 3)
    assert report.link_recall == pytest.approx(1 / 2)
    assert report.link_precision == pytest.approx(1 / 2)
    assert not report.passed


def test_a_missed_course_loses_its_links_and_fails_the_bar():
    labels = {"A1": label(), "B1": label(("A1",))}
    score = score_document("doc", ParseResult([Course("A1", credits=6, assessments=3)]), labels)
    report = AcceptanceReport((score,))
    assert score.missing_courses == ["B1"]
    assert report.course_recall == 0.5 and report.link_recall == 0.0
    assert "FAIL" in report.report()


def test_detail_accuracy_is_reported_but_does_not_decide_the_result():
    labels = {"A1": label(credits=6, assessments=3)}
    parsed = ParseResult([Course("A1", credits=3, assessments=9)])
    report = AcceptanceReport((score_document("doc", parsed, labels),))
    assert report.credits_accuracy == 0.0 and report.assessments_accuracy == 0.0
    assert report.passed


def test_nothing_parsed_from_a_labelled_document_fails():
    labels = {"A1": label()}
    report = AcceptanceReport((score_document("doc", ParseResult(), labels),))
    assert not report.passed
    assert not AcceptanceReport(()).passed


def test_labels_are_read_from_json(tmp_path):
    path = tmp_path / "doc.json"
    path.write_text(
        json.dumps({"comp1117": {"credits": 6, "prerequisites": [["MATH1013", "MATH1853"]]}})
    )
    assert load_labels(path) == {
        "COMP1117": CourseLabel(6, None, frozenset({frozenset({"MATH1013", "MATH1853"})}))
    }


def test_a_label_without_a_document_is_an_error_not_a_skip(tmp_path):
    (tmp_path / "ghost.json").write_text("{}")
    with pytest.raises(FileNotFoundError, match="ghost.json"):
        evaluate_folders(tmp_path, [tmp_path])


def test_command_line_reports_and_sets_exit_code(capsys, tmp_path):
    assert main([str(LABELS), *map(str, DOCUMENT_DIRS), str(SAMPLES)]) == 0
    assert "PASS" in capsys.readouterr().out

    (tmp_path / "doc.txt").write_text("COMP1117 Programming (6 credits)\n")
    (tmp_path / "doc.json").write_text(json.dumps({"COMP1117": {"prerequisites": [["X1"]]}}))
    assert main([str(tmp_path), str(tmp_path)]) == 1
    output = capsys.readouterr().out
    assert "missing link: COMP1117 needs X1" in output and "FAIL" in output

    assert main([str(LABELS)]) == 2
    (tmp_path / "ghost.json").write_text("{}")
    assert main([str(tmp_path), str(tmp_path / "nowhere")]) == 2
