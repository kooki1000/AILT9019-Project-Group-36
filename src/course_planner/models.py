"""Shared data structures used by every stage of the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field

# Prerequisites are stored in conjunctive normal form: a course is unlocked when
# *every* group is satisfied, and a group is satisfied when *any* course in it
# has been completed. "A and (B or C)" becomes ((A,), (B, C)).
PrereqGroups = tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class Course:
    """A course extracted from a requirement document."""

    code: str
    title: str = ""
    credits: int | None = None
    prerequisites: PrereqGroups = ()
    # Number of graded assessments (assignments, quizzes, exams, ...), if the
    # document states it. ``None`` means "unknown", not "zero".
    assessments: int | None = None

    @property
    def prerequisite_codes(self) -> frozenset[str]:
        """Every course code mentioned in any prerequisite group."""
        return frozenset(code for group in self.prerequisites for code in group)


@dataclass
class ParseResult:
    """Outcome of parsing one requirement document.

    Problems are collected as human-readable ``warnings`` instead of being
    raised, so the app can show them to the student rather than silently
    dropping courses.
    """

    courses: list[Course] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def by_code(self) -> dict[str, Course]:
        return {course.code: course for course in self.courses}
