from course_planner.models import Course, ParseResult


def test_prerequisite_codes_flattens_groups():
    course = Course("COMP3314", prerequisites=(("COMP2119",), ("MATH1013", "MATH1853")))
    assert course.prerequisite_codes == {"COMP2119", "MATH1013", "MATH1853"}


def test_by_code_indexes_courses():
    result = ParseResult(courses=[Course("COMP1117"), Course("COMP2113")])
    assert set(result.by_code()) == {"COMP1117", "COMP2113"}
