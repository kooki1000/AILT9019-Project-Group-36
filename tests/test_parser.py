from pathlib import Path

import pytest

from course_planner.parser import (
    EmptyDocumentError,
    UnsupportedFileError,
    count_assessments,
    parse_completed_courses,
    parse_csv,
    parse_document,
    parse_text,
)
from course_planner.prerequisites import parse_prerequisites

SAMPLE = Path(__file__).parent.parent / "data" / "samples" / "sample_requirements.txt"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("None", ()),
        ("-", ()),
        ("", ()),
        ("COMP1117", (("COMP1117",),)),
        ("COMP2113 and COMP2119", (("COMP2113",), ("COMP2119",))),
        ("COMP2113, COMP2119", (("COMP2113",), ("COMP2119",))),
        ("COMP2119 or STAT2601", (("COMP2119", "STAT2601"),)),
        (
            "COMP1117 and (MATH1013 or MATH1853)",
            (("COMP1117",), ("MATH1013", "MATH1853")),
        ),
        ("comp1117 / comp1118", (("COMP1117", "COMP1118"),)),
        ("COMP1117 and COMP1117", (("COMP1117",),)),
    ],
)
def test_parse_prerequisites(text, expected):
    assert parse_prerequisites(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("3 assignments, 1 midterm, 1 final exam", 5),
        ("assignments, project, final exam", 3),
        ("5", 5),
        ("40% coursework, 60% exam", 2),
        ("None", None),
        ("", None),
    ],
)
def test_count_assessments(text, expected):
    assert count_assessments(text) == expected


def test_sample_document_parses_every_course():
    result = parse_document(SAMPLE)
    assert [c.code for c in result.courses] == [
        "COMP1117", "COMP2113", "COMP2119", "COMP3230", "COMP3314", "MATH1013", "STAT2601",
    ]
    assert result.warnings == []

    courses = result.by_code()
    assert courses["COMP1117"].title == "Computer Programming"
    assert courses["COMP1117"].credits == 6
    assert courses["COMP1117"].prerequisites == ()
    assert courses["COMP1117"].assessments == 5
    assert courses["COMP2119"].prerequisites == (("COMP1117",), ("MATH1013", "MATH1853"))
    assert courses["COMP3230"].prerequisites == (("COMP2113",), ("COMP2119",))
    assert courses["COMP3314"].prerequisites == (("COMP2119", "STAT2601"),)
    assert courses["COMP3314"].assessments == 3


def test_single_line_pipe_format():
    result = parse_text(
        "COMP1117 | Computer Programming | 6 credits | Prerequisite: None\n"
        "COMP2113 | Programming Technologies | 6 credits | Prerequisite: COMP1117\n"
    )
    assert [(c.code, c.title, c.credits) for c in result.courses] == [
        ("COMP1117", "Computer Programming", 6),
        ("COMP2113", "Programming Technologies", 6),
    ]
    assert result.courses[1].prerequisites == (("COMP1117",),)


def test_inline_attributes_and_bullets():
    result = parse_text(
        "- COMP2113 Programming Technologies (6 credits) Prerequisite: COMP1117\n"
        "- COMP1117 Computer Programming (6 credits)\n"
    )
    assert [c.code for c in result.courses] == ["COMP2113", "COMP1117"]
    assert result.courses[0].title == "Programming Technologies"
    assert result.courses[0].prerequisites == (("COMP1117",),)


def test_wrapped_prerequisite_line_is_not_a_new_course():
    result = parse_text(
        "COMP3314 Machine Learning (6 credits)\n"
        "Prerequisite: COMP2119 or\n"
        "STAT2601\n"
        "COMP1117 Computer Programming (6 credits)\n"
    )
    assert [c.code for c in result.courses] == ["COMP3314", "COMP1117"]
    assert result.courses[0].prerequisites == (("COMP2119", "STAT2601"),)


def test_missing_credits_and_duplicates_are_reported():
    result = parse_text(
        "COMP1117 | Computer Programming\n"
        "COMP1117 | Computer Programming again | 6 credits\n"
    )
    assert len(result.courses) == 1
    assert any("credits were not found" in w for w in result.warnings)
    assert any("more than once" in w for w in result.warnings)


def test_text_without_courses_warns():
    result = parse_text("Welcome to the faculty. Please see an adviser.")
    assert result.courses == []
    assert result.warnings


def test_empty_text_raises():
    with pytest.raises(EmptyDocumentError):
        parse_text("   \n ")


def test_parse_csv():
    result = parse_csv(
        "Code,Title,Credits,Prerequisites,Assessments\n"
        "COMP1117,Computer Programming,6,None,3 assignments; 1 exam\n"
        "COMP2119,Data Structures,6,COMP1117 and (MATH1013 or MATH1853),4\n"
        ",,,,\n"
        "nonsense,Bad row,6,,\n"
    )
    assert [c.code for c in result.courses] == ["COMP1117", "COMP2119"]
    assert result.courses[0].assessments == 4
    assert result.courses[1].assessments == 4
    assert result.courses[1].prerequisites == (("COMP1117",), ("MATH1013", "MATH1853"))
    assert any("Row 5" in w for w in result.warnings)


def test_csv_requires_code_column():
    with pytest.raises(EmptyDocumentError):
        parse_csv("title,credits\nProgramming,6\n")


def test_parse_document_dispatches_on_extension():
    csv_bytes = b"code,credits\nCOMP1117,6\n"
    assert parse_document(csv_bytes, "plan.csv").courses[0].credits == 6
    assert parse_document(b"COMP1117 Programming (6 credits)", "plan.txt").courses[0].code == (
        "COMP1117"
    )


def test_unsupported_file_type_gives_plain_message():
    with pytest.raises(UnsupportedFileError, match="PDF, plain text"):
        parse_document(b"data", "plan.docx")


def test_unreadable_pdf_gives_plain_message():
    with pytest.raises(EmptyDocumentError, match="could not be read"):
        parse_document(b"not really a pdf", "plan.pdf")


def test_parse_completed_courses_tolerates_spacing_and_case():
    assert parse_completed_courses("comp 1117, MATH1013\nCOMP2113") == {
        "COMP1117", "MATH1013", "COMP2113",
    }


def test_pipe_separated_line_is_read_once():
    # Regression: the fields of a one-line course used to be processed twice, which
    # doubled the assessment count and invented an extra prerequisite group.
    course = parse_text(
        "STAT3001 | Applied Modelling | 6 credits | Prerequisite: STAT2001 and STAT1002 | "
        "Assessment: 2 assignments, 1 project, 1 final exam\n"
    ).courses[0]
    assert course.assessments == 4
    assert course.prerequisites == (("STAT2001",), ("STAT1002",))


def test_section_heading_is_not_counted_as_an_assessment():
    # Regression: "Core courses and electives" was split on "and" and counted as an extra item.
    result = parse_text(
        "MATH1005 Calculus (6 credits)\n"
        "  Prerequisite: None\n"
        "  Assessment: 3 quizzes, 1 midterm, 1 final exam\n"
        "\n"
        "B. Core courses and electives\n"
        "DASC2001 Statistical Learning (6 credits)\n"
        "  Prerequisite: MATH1005\n"
        "\n"
        "C. Advanced courses and projects\n"
        "DASC3001 Machine Learning (6 credits)\n"
    )
    assert result.by_code()["MATH1005"].assessments == 5
    assert result.by_code()["DASC2001"].prerequisites == (("MATH1005",),)


def test_wrapped_assessment_and_bracketed_prerequisite_still_continue():
    course = parse_text(
        "COMP2119 Data Structures (6 credits)\n"
        "Prerequisite: COMP1117 and (MATH1013\n"
        "or MATH1853)\n"
        "Assessment: 3 assignments, 1 midterm and\n"
        "1 final exam\n"
    ).courses[0]
    assert course.prerequisites == (("COMP1117",), ("MATH1013", "MATH1853"))
    assert course.assessments == 5


@pytest.mark.parametrize(
    "header", ["Pre-requisites", "Prerequisite(s)", "PRE-REQ", "Pre requisites"]
)
def test_csv_prerequisite_column_name_variants(header):
    result = parse_csv(f"Course Code,Units,{header}\nCOMP2113,6,COMP1117\n")
    assert result.courses[0].credits == 6
    assert result.courses[0].prerequisites == (("COMP1117",),)
