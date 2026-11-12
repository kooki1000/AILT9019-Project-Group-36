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
    assert len(report.documents) == 6
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
        # an exam level is an alternative route, so the group cannot be enforced
        ("Level 2 in Module 1, or Module 2 of HKDSE Mathematics, or Pass in MATH1011.", ()),
        ("COMP1117 or Level 3 in HKDSE Mathematics", ()),
        # taking courses together is not a prerequisite
        ("MATH1011, or take MATH1011 and MATH1853 concurrently.", (("MATH1011",),)),
        # ", or" extends the list of alternatives instead of starting a new requirement
        ("COMP2113, or COMP2123, or ENGG1340", (("COMP2113", "COMP2123", "ENGG1340"),)),
        # "or equivalent" / approval do not remove the course requirement
        ("COMP2119 or equivalent", (("COMP2119",),)),
        ("COMP2119 or special approval by instructor", (("COMP2119",),)),
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


def test_law_style_lists_without_a_period_after_the_code():
    result = parsed("law_style.txt")
    by = result.by_code()
    # Wrapped regulation sentences ("Subject to LL11, ...", "4 Candidates shall take ...") are
    # not headings; the compulsory lists are required, "choose one" lists and electives are not.
    assert codes(result, elective=False) == [
        "LLAW1001", "LLAW1002", "AILT1001", "CAES1001", "LLAW1005",
    ]
    assert {"LLAW3148", "LLAW3187", "LLAW3016", "LLAW3015", "LLAW3230"} <= set(
        codes(result, elective=True)
    )
    assert "LLAW3205" in by and by["LLAW3205"].elective  # listed under "choose one" earlier
    assert not any(c.code.startswith(("LLAWxxxx", "CCXX")) for c in result.courses)


def test_credits_given_once_for_a_whole_choose_one_list():
    by = parsed("law_style.txt").by_code()
    assert by["LLAW3230"].credits == 6  # "(6 credits)" is in the heading above its list
    assert by["LLAW3148"].credits is None  # that heading gives no credits
    assert by["LLAW3015"].credits is None  # no per-course credits anywhere: left empty


def test_a_section_heading_is_not_taken_as_a_titles_credits():
    # "SECOND YEAR (63 credits)" follows a creditless entry; 63 is not CAES1001's credits.
    assert parsed("law_style.txt").by_code()["CAES1001"].credits is None


def test_descriptions_and_lists_merge_for_plain_headers():
    by = parsed("law_style.txt").by_code()
    assert by["LLAW1001"].assessments == 2 and not by["LLAW1001"].elective
    assert by["LLAW3205"].prerequisites == (("LLAW2001",),)


def test_either_or_requirement_makes_its_listed_courses_choices():
    result = parse_text(
        "Core courses (12 credits)\n"
        "JMSC2001. Media law (6 credits)\n"
        "Faculty Global Citizenship Requirement (12 credits)\n"
        "Candidates must either complete FOSS2019, or a combination of two 6-credit\n"
        "FOSS2019. Global Citizenship internship (12 credits)\n"
        "FOSS2022. Global intensive learning programme (6 credits)\n"
    )
    assert codes(result, elective=False) == ["JMSC2001"]
    assert set(codes(result, elective=True)) == {"FOSS2019", "FOSS2022"}


def test_a_title_containing_another_course_code_is_a_sentence():
    from course_planner.parser import _plausible_title

    assert not _plausible_title("Basic Spoken Cantonese for Mandarin, or CUND9002 Practical")
    assert _plausible_title("Basic Spoken Cantonese for Mandarin Speakers")


def test_a_file_with_several_degrees_reads_one_at_a_time():
    result = parsed("multi_programme.txt")
    assert result.programmes == ["COMPUTER ENGINEERING", "ELECTRICAL ENGINEERING"]
    assert result.programme == "COMPUTER ENGINEERING"  # the first, by default
    assert codes(result, elective=False) == ["ENGG1000", "COMP2113", "ELEC2441", "COMP3230"]
    assert "ELEC2147" not in result.by_code()  # a course of the other degree only


def test_choosing_another_degree_changes_the_required_courses():
    result = parse_document(SYLLABI / "multi_programme.txt", programme="electrical engineering")
    assert result.programme == "ELECTRICAL ENGINEERING"
    assert codes(result, elective=False) == ["ENGG1000", "ELEC2147", "ELEC3141"]
    assert "COMP3230" not in result.by_code() and "ELEC2441" not in result.by_code()
    # COMP2113 is only described here, so it is available but not required.
    assert result.by_code()["COMP2113"].elective


def test_minor_tables_after_a_degree_are_not_part_of_it():
    result = parse_document(SYLLABI / "multi_programme.txt", programme="ELECTRICAL ENGINEERING")
    assert "ELEC9999" not in result.by_code()


def test_descriptions_after_a_closed_section_still_add_prerequisites():
    by = parsed("multi_programme.txt").by_code()
    assert by["COMP2113"].prerequisites == (("ENGG1000", "ENGG1330"),)
    electrical = parse_document(SYLLABI / "multi_programme.txt", programme="ELECTRICAL ENGINEERING")
    assert electrical.by_code()["ELEC3141"].prerequisites == (("ELEC2147",),)


def test_unknown_programme_falls_back_to_the_first_with_a_warning():
    result = parse_document(SYLLABI / "multi_programme.txt", programme="Civil Engineering")
    assert result.programme == "COMPUTER ENGINEERING"
    assert any("Civil Engineering" in w for w in result.warnings)


def test_single_programme_documents_report_no_programmes():
    assert parsed("list_style.txt").programmes == []


def test_a_course_is_never_its_own_prerequisite():
    course = parse_text(
        "MATH1853. Linear algebra (6 credits)\n"
        "Prerequisite: MATH1011 or MATH1853\n"
    ).courses[0]
    assert course.prerequisites == (("MATH1011",),)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # "A or (B and C)" is expanded into the app's AND-of-OR form
        (
            "ELEC2543 Object-oriented programming or (COMP2119 Data structures and COMP2396 Java)",
            (("ELEC2543", "COMP2119"), ("ELEC2543", "COMP2396")),
        ),
        ("(AAAA1111 or BBBB2222) and CCCC3333", (("AAAA1111", "BBBB2222"), ("CCCC3333",))),
        # the "and" of a title is not a connector
        (
            "ENGG1111 Computer programming and applications or ENGG1112 or ENGG1330",
            (("ENGG1111", "ENGG1112", "ENGG1330"),),
        ),
        # quotes around a title do not hide the code; "and either ..." is a real "and"
        ("\u201cCHIN9501 Chinese as a foreign language I\u201d or equivalent", (("CHIN9501",),)),
        ("PSYC1004 and either PSYC2007 or PSYC2051.", (("PSYC1004",), ("PSYC2007", "PSYC2051"))),
        # a grade on a course is not another route around it
        ("COMP2119 (Grade B or above) or special approval", (("COMP2119",),)),
        ("COMP2119 with grade B", (("COMP2119",),)),
        # "Pass in X" is just X
        ("Level 2 in HKDSE Mathematics or Pass in MATH1011", ()),
        # a clause implied by a smaller one is redundant
        ("COMP1117 and (COMP1117 or COMP1118)", (("COMP1117",),)),
        ("COMP1117; and COMP1118 or COMP1119", (("COMP1117",), ("COMP1118", "COMP1119"))),
        # unbalanced brackets fall back to the flat reading instead of failing
        ("COMP1117 and (COMP1118 or COMP1119", (("COMP1117",), ("COMP1118", "COMP1119"))),
    ],
)
def test_prerequisite_grammar(text, expected):
    assert parse_prerequisites(text) == expected


def test_a_no_course_alternative_is_kept_only_when_its_course_is_in_the_document():
    result = parse_text(
        "GRMN1001. German I.1 (6 credits)\n"
        "Prerequisite: Nil\n"
        "GRMN2001. German II.1 (6 credits)\n"
        "Prerequisite: GRMN1001 or comparable level acquired elsewhere.\n"
        "MATH1851. Calculus (6 credits)\n"
        "Prerequisite: Level 2 in HKDSE Mathematics, or Pass in MATH1011.\n"
    )
    by = result.by_code()
    assert by["GRMN2001"].prerequisites == (("GRMN1001",),)  # usable for ordering
    assert by["MATH1851"].prerequisites == ()  # MATH1011 is not in the document
    assert any("MATH1851" in w and "not (only) course codes" in w for w in result.warnings)
