"""Measure how evenly a plan spreads difficulty across semesters.

"More evenly distributed" means a lower variance of the per-semester total
difficulty score. The baseline plan to beat takes courses in the order the
requirement document lists them (see ``planner.baseline_plan``).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

# Used for a course that has no entry in the difficulty mapping.
DEFAULT_DIFFICULTY = 5.5


def semester_loads(
    semesters: Sequence[Sequence[str]], difficulty: Mapping[str, float]
) -> list[float]:
    """Total difficulty score of each semester."""
    return [sum(difficulty.get(code, DEFAULT_DIFFICULTY) for code in sem) for sem in semesters]


def load_variance(semesters: Sequence[Sequence[str]], difficulty: Mapping[str, float]) -> float:
    """Population variance of the per-semester total difficulty (0 for no semesters)."""
    loads = semester_loads(semesters, difficulty)
    if not loads:
        return 0.0
    mean = sum(loads) / len(loads)
    return sum((load - mean) ** 2 for load in loads) / len(loads)


@dataclass(frozen=True)
class VarianceComparison:
    plan_variance: float
    baseline_variance: float

    @property
    def more_even(self) -> bool:
        """True only when the plan is strictly more even than the baseline."""
        return self.plan_variance < self.baseline_variance


def compare_to_baseline(
    plan: Sequence[Sequence[str]],
    baseline: Sequence[Sequence[str]],
    difficulty: Mapping[str, float],
) -> VarianceComparison:
    return VarianceComparison(
        plan_variance=load_variance(plan, difficulty),
        baseline_variance=load_variance(baseline, difficulty),
    )
