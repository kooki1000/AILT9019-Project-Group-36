# AILT9019 Project – Group 36: HKU Course Planner

A local Python tool that turns a programme's requirement document into a
semester-by-semester course plan, balanced by an estimated difficulty score.
It is a *draft-plan helper*, not an official graduation audit, and it does not
replace an academic adviser. Nothing you upload leaves your machine.

## Pipeline

1. **Parse** a requirement document (PDF, plain text or CSV) into courses and prerequisites.
2. **Load reviews** from a local, offline RIC dataset (no HKU/RIC password is ever used).
3. **Translate** Chinese reviews to English offline.
4. **Score** each course's difficulty from 1 to 10 (credits 35%, assessments 35%, reviews 30%).
5. **Plan** courses across semesters, respecting prerequisites and a load limit.
6. **Adjust** the plan by hand; every edit re-checks prerequisites and load.

See the project proposal for the full design and evaluation criteria.

## Status

| Must-have                                   | Status      |
| ------------------------------------------- | ----------- |
| 1. Parse requirement document               | built (95% bar not yet measured) |
| 2. Retrieve reviews from local RIC dataset  | todo        |
| 3. Detect and translate Chinese reviews     | built (not yet wired into the app) |
| 4. 1–10 difficulty score with fallback rule | built       |
| 5. Multi-semester plan generator            | built       |
| 6. Review and adjust the plan               | todo        |
| 7. Flag prerequisite conflicts              | built       |

## Setup

Requires Python 3.10+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Offline translation (Chinese reviews)

Chinese reviews are translated to English on your own computer with the
open-source `Helsinki-NLP/opus-mt-zh-en` model; nothing is sent to any service.
It needs a one-time setup that downloads the model (a few hundred MB):

```bash
pip install -e ".[translation]"
python -m course_planner.translation download
python -m course_planner.translation translate "這門課功課很多"
```

Machine translation can miss tone and idioms, so original reviews are always
kept next to their translations. `export_review_sample` writes a CSV of
translated reviews for a Chinese-reading teammate to spot-check.

## Development

```bash
pytest          # run the tests
ruff check .    # lint
```

Check the plan generator against a folder of requirement documents (every plan
must contain each course once, respect prerequisites and stay under the load
limit, and be more even than document order in at least 4 of 5 cases):

```bash
python -m course_planner.evaluation tests/fixtures/requirements
```
