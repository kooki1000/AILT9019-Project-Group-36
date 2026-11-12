"""Acceptance checks from the proposal's evaluation section.

For every test document the generated plan must pass three checks: each
required course appears exactly once, no course precedes its prerequisite, and
no semester exceeds the credit or course-load limit. "Better" means a lower
variance of per-semester difficulty than the document-order baseline. A run
passes when at least 4 of 5 cases meet every check *and* at least 4 of 5 are
more even than the baseline (thresholds fixed before testing).

Run on a folder of requirement documents::

    python -m course_planner.evaluation tests/fixtures/requirements
"""

from __future__ import annotations

import sys
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from course_planner.difficulty import difficulty_score
from course_planner.metrics import load_variance
from course_planner.models import Course
from course_planner.parser import SUPPORTED_EXTENSIONS, parse_document
from course_planner.planner import Issue, PlanConstraints, check_plan, generate_plan

PASS_THRESHOLD = 4  # of 5 constructed cases


@dataclass(frozen=True)
class CaseEvaluation:
    name: str
    issues: tuple[Issue, ...]
    semesters: int
    plan_variance: float
    baseline_variance: float

    @property
    def checks_passed(self) -> bool:
        """All three checklist items hold and nothing was flagged or left out."""
        return not self.issues

    @property
    def more_even(self) -> bool:
        return self.plan_variance < self.baseline_variance


@dataclass(frozen=True)
class SuiteEvaluation:
    cases: tuple[CaseEvaluation, ...]
    threshold: int = PASS_THRESHOLD

    @property
    def checks_passing(self) -> int:
        return sum(case.checks_passed for case in self.cases)

    @property
    def more_even_count(self) -> int:
        return sum(case.more_even for case in self.cases)

    @property
    def passed(self) -> bool:
        return self.checks_passing >= self.threshold and self.more_even_count >= self.threshold

    def report(self) -> str:
        lines = [f"{'case':<40}{'checks':<8}{'sems':<6}{'plan var':<10}{'baseline var':<13}better"]
        for case in self.cases:
            lines.append(
                f"{case.name:<40}{'ok' if case.checks_passed else 'FAIL':<8}{case.semesters:<6}"
                f"{case.plan_variance:<10.2f}{case.baseline_variance:<13.2f}"
                f"{'yes' if case.more_even else 'no'}"
            )
            lines.extend(f"    ! {issue.message}" for issue in case.issues)
        lines.append(
            f"checks passed: {self.checks_passing}/{len(self.cases)}; "
            f"more even than baseline: {self.more_even_count}/{len(self.cases)}; "
            f"need {self.threshold} for each -> {'PASS' if self.passed else 'FAIL'}"
        )
        return "\n".join(lines)


def evaluate_case(
    name: str,
    courses: Sequence[Course],
    completed: Collection[str] = (),
    constraints: PlanConstraints = PlanConstraints(),  # noqa: B008
    difficulty: Mapping[str, float] | None = None,
) -> CaseEvaluation:
    """Plan one document and run the three checks plus the variance comparison.

    Without ``difficulty``, every course is scored review-free from the document.
    """
    if difficulty is None:
        difficulty = {c.code: difficulty_score(c).score for c in courses}
    result = generate_plan(courses, completed, difficulty, constraints)

    required = [c.code for c in courses if c.code not in set(completed)]
    catalog = {c.code: c for c in courses}
    issues = list(result.issues)
    # Re-check independently of the generator: anything missing, duplicated,
    # out of order or over the limit counts against the case.
    issues.extend(
        issue
        for issue in check_plan(result.semesters, catalog, completed, constraints, required)
        if issue not in issues
    )
    return CaseEvaluation(
        name=name,
        issues=tuple(issues),
        semesters=len(result.semesters),
        plan_variance=load_variance(result.semesters, difficulty),
        baseline_variance=load_variance(result.baseline, difficulty),
    )


def evaluate_directory(
    directory: Path,
    constraints: PlanConstraints = PlanConstraints(),  # noqa: B008
) -> SuiteEvaluation:
    files = sorted(p for p in directory.iterdir() if p.suffix.lower() in SUPPORTED_EXTENSIONS)
    # Electives and "choose one" options are not required, so they are not planned as if they were.
    cases = [
        evaluate_case(
            path.stem,
            [c for c in parse_document(path).courses if not c.elective],
            constraints=constraints,
        )
        for path in files
    ]
    return SuiteEvaluation(tuple(cases))


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: python -m course_planner.evaluation <folder of requirement documents>")
        return 2
    suite = evaluate_directory(Path(args[0]))
    print(suite.report())
    return 0 if suite.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
