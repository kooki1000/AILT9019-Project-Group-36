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
| 3. Detect and translate Chinese reviews     | built as a team tool for dataset preparation (not yet wired into the app) |
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

## Preparing the review dataset (team only)

**You do not need this section to use the app.** The app never translates
anything itself: it reads a review dataset that already contains English text,
so it needs no model, no extra install and no API key.

Chinese reviews are translated once, by the team, when the dataset is built:

1. Run the offline translator over the collected reviews on one machine. It uses
   the open-source `Helsinki-NLP/opus-mt-zh-en` model, so nothing is sent to any
   service. This needs a one-time download of the model and PyTorch, which is
   large (hundreds of MB to a few GB):

   ```bash
   pip install -e ".[translation]"
   python -m course_planner.translation download
   python -m course_planner.translation translate "這門課功課很多"   # quick test
   ```

2. Have a Chinese-reading teammate spot-check the output.
   `export_review_sample` writes a CSV of random translated reviews with blank
   `adequate` and `notes` columns to fill in. Machine translation can miss tone
   and idioms, and the model is weaker on colloquial Cantonese.
3. Ship the checked dataset with both the original and the English text, so any
   score can be traced back to its source.

Reviews that are still untranslated when the app loads them are left out of the
difficulty score, and the app says so.

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
