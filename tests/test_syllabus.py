"""Real faculty syllabuses differ from the team's own documents: tables, descriptions, lists."""

from pathlib import Path

import pytest

from course_planner.parser import parse_document, parse_text
from course_planner.parsing_eval import evaluate_folders
from course_planner.prerequisites import parse_prerequisites
from pdfutil import make_pdf

FIXTURES = Path(__file__).parent / "fixtures"
SYLLABI = FIXTURES / "syllabi"
LABELS = FIXTURES / "labels_syllabi"


def parsed(name: str):
    return parse_document(SYLLABI / name)


def codes(result, elective: bool) -> list[str]:
    return [c.code for c in result.courses if c.elective is elective]


def test_syllabus_layouts_meet_the_acceptance_bar():
    report = evaluate_folders(LABELS, [SYLLABI])
    assert len(report.documents) == 4
    assert report.passed, report.report()
    for doc in report.documents:  # exact: nothing missing, nothing invented from prose
        assert not doc.missing_courses and not doc.extra_courses, doc.name
        assert not doc.missing_links and not doc.extra_links, doc.name


def test_syllabus_layouts_survive_the_pdf_path():
    for name in ("table_year_column.txt", "tables_and_descriptions.txt"):
        text = (SYLLABI / name).read_text()
        from_pdf = parse_document(make_pdf(text), "doc.pdf")
        assert [c.code for c in from_pdf.courses] == [c.code for c in parsed(name).courses]


def test_table_rows_with_and_without_year_column():
    result = parsed("table_year_column.txt")
    by = result.by_code()
    assert by["ECON2210"].credits == 6 and by["ECON4294"].credits == 12
    assert by["CAES1001"].credits == 0
    assert by["CAES1001"].title == "Academic communication in English"
    assert by["ACCT1101"].title == "Introduction to financial accounting"  # footnote digit dropped
    assert by["CAES9920"].title == "Academic communication for business"
    # Neither the placeholder CCXXxxxx nor a code inside a prose sentence is a course.
    assert not any(c.code.startswith(("CCXX", "FINA")) for c in result.courses)


def test_choices_and_elective_lists_are_not_treated_as_required():
    result = parsed("table_year_column.txt")
    assert codes(result, elective=False) == [
        "CAES1001", "CAES9920", "ACCT1101", "ECON1210", "ECON2210", "ECON4200",
    ]
    assert {"ECON1280", "IIMT1640"} <= set(codes(result, elective=True))  # choose-one pair
    assert {"ECON2214", "ECON2216", "ECON4294"} <= set(codes(result, elective=True))


def test_second_programme_tables_and_focus_lists_are_not_requirements():
    result = parsed("tables_and_descriptions.txt")
    required = ["COMP1117", "COMP2113", "COMP2120", "COMP3230", "COMP3297"]
    assert codes(result, elective=False) == required
    by = result.by_code()
    assert "COMP4999" not in by  # table under "MINOR IN ..."
    assert by["COMP3251"].elective and by["COMP3252"].elective  # alternatives share credits
    assert by["COMP3252"].credits == 6
    assert by["COMP3340"].elective and by["COMP3340"].credits == 6  # only mentioned in a Focus list


def test_descriptions_add_prerequisites_and_assessments_to_table_courses():
    by = parsed("tables_and_descriptions.txt").by_code()
    assert by["COMP2113"].prerequisites == (("COMP1117", "ENGG1330"),)
    assert by["COMP3230"].prerequisites == (("COMP2113", "COMP2123"), ("COMP2120", "ELEC2441"))
    assert by["COMP3230"].title == "Principles of operating systems"  # wrapped title
    assert by["COMP1117"].prerequisites == ()  # "Mutually exclusive with" is not a prerequisite
    assert by["COMP1117"].assessments == 2  # prose "COMP2113 will build..." did not end the entry


def test_prerequisites_that_are_not_course_codes_are_reported_not_dropped():
    warnings = parsed("tables_and_descriptions.txt").warnings
    assert any("COMP3340" in w and "special approval" in w for w in warnings)
    catalogue = parsed("catalogue_descriptions.txt").warnings
    assert any("HIST3001" in w and "At least one 2000-level" in w for w in catalogue)
    assert not any("HIST1002" in w for w in catalogue)  # "Nil" means none


def test_catalogue_without_tables_leaves_courses_unclassified():
    result = parsed("catalogue_descriptions.txt")
    assert codes(result, elective=True) == []  # nothing says which are required
    by = result.by_code()
    assert by["HIST1002"].title == (
        "Modern China and the world: a survey of political, economic and social change"
    )
    assert by["HIST1002"].credits == 6  # "(6" and "credits)" were on different lines
    assert by["HIST2001"].prerequisites == (("HIST1001",), ("HIST1002", "HIST1003"))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("HIST1001. Non-permissible combination: HIST2099.", (("HIST1001",),)),
        ("COMP1117 Mutually exclusive with: ENGG1330", (("COMP1117",),)),
        ("XXXX2002 course or HIST1001", (("HIST1001",),)),
        ("Nil.", ()),
    ],
)
def test_prerequisite_text_ignores_restrictions_and_placeholders(text, expected):
    assert parse_prerequisites(text) == expected


def test_prose_starting_with_a_code_does_not_create_a_course():
    result = parse_text(
        "Course code Course title Credits\n"
        "COMP1117 Computer programming 6\n"
        "COMP2113 will not be counted towards the category of electives. If students\n"
    )
    assert [c.code for c in result.courses] == ["COMP1117"]


def test_prerequisite_list_wrapping_with_a_leading_connector_is_joined():
    course = parse_text(
        "COMP3340. Deep learning (6 credits)\n"
        "Prerequisites: COMP2119 or COMP2118; and MATH1853\n"
        "or MATH2014 or MATH1013\n"
    ).courses[0]
    assert course.prerequisites == (("COMP2119", "COMP2118"), ("MATH1853", "MATH2014", "MATH1013"))


def test_course_lists_are_classified_by_their_headings():
    result = parsed("list_style.txt")
    # Core courses are required; "A or / B or / C" alternatives, "in lieu" lists and
    # elective lists are not. Lines of description after a list entry do not hide a heading.
    assert codes(result, elective=False) == ["CAES1001", "JMSC1001", "JMSC1011"]
    assert {"CSSC9001", "CUND9001", "CUND9002", "CHIN9501"} <= set(codes(result, elective=True))
    assert {"JMSC2005", "JMSC2008"} <= set(codes(result, elective=True))


def test_list_entries_are_merged_with_their_later_description():
    by = parsed("list_style.txt").by_code()
    assert by["JMSC2005"].prerequisites == (("JMSC1011",),)
    assert by["JMSC1001"].assessments == 2  # "Assessment:" in the middle of a line
    assert not by["JMSC1001"].elective  # described later, but listed as core
    assert by["CAES1001"].title == "Academic Communication in English"  # footnote cut off
    assert by["CUND9002"].title.startswith("Practical Chinese and Hong Kong society")


def test_missing_credits_in_a_list_are_warned_about():
    warnings = parsed("list_style.txt").warnings
    assert any("CAES1001: credits were not found" in w for w in warnings)
    assert any("CHIN9501: credits were not found" in w for w in warnings)


def test_regulations_document_explains_why_there_are_no_courses():
    result = parse_text(
        "REGULATIONS FOR THE DEGREE OF\nBACHELOR OF ENGINEERING (BEng)\n"
        "Candidates may take CUND9001 or CUND9002 as a language course.\n"
    )
    assert result.courses == []
    assert any("regulations document" in w for w in result.warnings)


def test_a_missing_closing_bracket_after_credits_is_tolerated():
    text = "LLAW3146. Multiculturalism and the law (6 credits\nPrerequisite: Nil\n"
    course = parse_text(text).courses[0]
    assert course.credits == 6 and course.title == "Multiculturalism and the law"


def test_description_header_with_bare_trailing_credits():
    by = parse_text(
        "AILT1001. Artificial intelligence literacy I 3\n"
        "AILT9017. Digital literacy through a social sciences lens* 3\n"
    ).by_code()
    assert by["AILT1001"].credits == 3
    assert by["AILT1001"].title == "Artificial intelligence literacy I"
    assert by["AILT9017"].title == "Digital literacy through a social sciences lens"
