# AILT9019 Project – Group 36: HKU Course Planner

A local Python tool that turns a programme's requirement document into a
semester-by-semester course plan, balanced by an estimated difficulty score.
It is a *draft-plan helper*, not an official graduation audit, and it does not
replace an academic adviser. Nothing you upload leaves your machine.

## Pipeline

1. **Parse** a requirement document (PDF, plain text or CSV) into courses and prerequisites.
2. **Load prepared reviews** from a local CSV. The repository includes demonstration
   data; acquisition and approval of real RIC data are still pending.
3. **Use prepared translations** to include and audit Chinese review rows. Translation
   is optional team-side preprocessing and is not performed by the app; only the
   numeric rating contributes to the difficulty score.
4. **Score** each course's difficulty from 1 to 10 (credits 35%, assessments 35%,
   numeric review ratings 30%).
5. **Plan** courses across semesters, respecting prerequisites and a load limit.
6. **Adjust** the plan by hand; every edit re-checks prerequisites and load.

See the project proposal for the full design and evaluation criteria.

## Status

| Must-have                                   | Status |
| ------------------------------------------- | ------ |
| 1. Parse requirement document               | Built; the proposed 95% parsing target has not yet been measured |
| 2. Load a prepared local review CSV         | Built with bundled demonstration data; real RIC acquisition/provenance pending |
| 3. Detect and translate Chinese reviews     | Standalone preparation helper built; the app only reads prepared translations |
| 4. 1–10 difficulty score with fallback rule | Built; review input is a 1–5 numeric-rating proxy |
| 5. Multi-semester plan generator            | Built |
| 6. Review and adjust the plan               | Built |
| 7. Flag prerequisite conflicts              | Built for course-code prerequisites |

## Setup

Requires Python 3.10+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run the app

```bash
streamlit run src/course_planner/app.py
```

The app opens in your browser. Pick **Use the sample document** and press
**Build my plan** to see a draft plan straight away, then move courses between
semesters or add electives; every change is re-checked immediately. Uploaded
documents and their parsed results are kept in a local SQLite file
(`.course_planner/app.sqlite3`) and can be deleted from the sidebar. Set
`COURSE_PLANNER_DB` to store it somewhere else.

The difficulty score also reads prepared review rows from a local dataset
(`data/reviews/sample_reviews.csv`); set `COURSE_PLANNER_REVIEWS` to point at
your own prepared dataset. Without a dataset the score uses the requirement
document only.

## Reproducible sample

With the bundled requirement document, bundled demonstration review CSV and
default limits, **Build my plan** currently gives:

| Semester | Courses |
| -------- | ------- |
| 1 | COMP1117, MATH1013 |
| 2 | COMP2113, COMP2119, STAT2601 |
| 3 | COMP3230, COMP3314 |

The run parses 7 courses without warnings, loads 20 usable demonstration review
rows covering all 7 courses, and reports no unscheduled courses or plan issues.
Changing completed courses, semester limits or `COURSE_PLANNER_REVIEWS` can
change the result.

## Review dataset

The bundled `data/reviews/sample_reviews.csv` is demonstration data and is not
claimed to be real RIC data. A custom CSV uses these columns:

```text
course_code,text,rating,translation
```

- `course_code`, `text` and `rating` are required for a row to contribute.
- The current rating scale is 1 (lowest) to 5 (highest). It is mapped to a
  difficulty proxy; the app does not perform sentiment analysis on review text.
- An English review can leave `translation` blank. A Chinese review needs a
  prepared English `translation`; otherwise it is excluded from the score.
- The app reports how many rows were loaded and how many were excluded. A course
  without usable reviews falls back to credits and assessment count, rescaled
  equally across the full 1–10 range.

Before adding real review data, the team must confirm collection and reuse are
permitted, remove personal identifiers, and avoid committing account details or
other private information.

## Preparing the review dataset (team only)

**You do not need this section to use the app.** The app never translates
anything itself: it reads a review dataset that already contains English text,
so it needs no model, no extra install and no API key.

Chinese reviews can be translated once, by the team, when the dataset is built:

1. Install the optional translation dependencies and download the
   `Helsinki-NLP/opus-mt-zh-en` model. Installation and the first model download
   require internet access; translation then runs locally. PyTorch and the model
   can require hundreds of MB to a few GB:

   ```bash
   pip install -e ".[translation]"
   python -m course_planner.translation download
   python -m course_planner.translation translate "這門課功課很多"   # quick test
   ```

   The CLI command above is a quick text check, not a CSV batch-import command.
   The app itself never invokes the translator.

2. Have a Chinese-reading teammate spot-check the output.
   `export_review_sample` writes a CSV of random translated reviews with blank
   `adequate` and `notes` columns to fill in. Machine translation can miss tone
   and idioms, and the model is weaker on colloquial Cantonese.
3. Ship the checked dataset with both the original and the English text, so any
   score can be traced back to its source.

Reviews that are still untranslated when the app loads them are left out of the
difficulty score, and the app says so.

## Data and privacy

The running app does not send requirement documents or review data to a remote
service. Successfully parsed inputs and their parsed JSON are stored in the
local SQLite file `.course_planner/app.sqlite3`; the sidebar can delete its saved
rows. Package installation and the optional first translation-model download do
use the internet.

## Development

```bash
python -m pytest -q       # run the complete test suite, including Streamlit UI tests
python -m pytest -q --ignore=tests/test_app.py  # run the non-UI suite only
python -m ruff check .    # lint
```

Check the plan generator against a folder of requirement documents (every plan
must contain each course once, respect prerequisites and stay under the load
limit, and be more even than document order in at least 4 of 5 cases):

```bash
python -m course_planner.evaluation tests/fixtures/requirements
```

For the five bundled constructed fixtures, the current result is 5/5 legality
checks, 4/5 plans more even than document-order baseline, and overall `PASS`.
This evaluation uses document-only difficulty scores; it does not validate the
review dataset. In the supplied archive, 232 non-UI tests passed on 26 October
2026. The full Streamlit UI suite should also be run in the project environment
before submission.

## Parser as an agent skill

`skills/parse-requirements/SKILL.md` packages the document parser for other agent
environments. It calls `python -m course_planner.parse_cli <file>`, which prints
the courses, prerequisites and warnings as JSON.

## Known limitations

- The proposed 95% parsing target has not been measured on a labelled corpus.
- The bundled reviews are demonstration data; real RIC acquisition, permission,
  provenance and evaluation are pending.
- Review influence is derived from a numeric 1–5 rating, not review-text
  sentiment analysis. Translation quality has not been evaluated on real RIC
  or colloquial Cantonese data.
- Prerequisite checking recognises course codes. Conditions such as year
  standing, department approval and other non-code rules are not enforced.
- Semester availability, timetable clashes, double majors, transfer credits and
  requirement waivers are outside the current scope.
- This is a planning aid, not an official HKU graduation audit or difficulty
  rating; students must verify the result with current programme rules and an
  academic adviser.
# AILT9019 Project – Group 36: HKU Course Planner

A local Python tool that turns a programme's requirement document into a
semester-by-semester course plan, balanced by an estimated difficulty score.
It is a *draft-plan helper*, not an official graduation audit, and it does not
replace an academic adviser. Nothing you upload leaves your machine.

## Pipeline

1. **Parse** a requirement document (PDF, plain text or CSV) into courses and prerequisites.
2. **Load prepared reviews** from a local CSV. The repository includes demonstration
   data; acquisition and approval of real RIC data are still pending.
3. **Use prepared translations** to include and audit Chinese review rows. Translation
   is optional team-side preprocessing and is not performed by the app; only the
   numeric rating contributes to the difficulty score.
4. **Score** each course's difficulty from 1 to 10 (credits 35%, assessments 35%,
   numeric review ratings 30%).
5. **Plan** courses across semesters, respecting prerequisites and a load limit.
6. **Adjust** the plan by hand; every edit re-checks prerequisites and load.

See the project proposal for the full design and evaluation criteria.

## Status

| Must-have                                   | Status |
| ------------------------------------------- | ------ |
| 1. Parse requirement document               | Built; the proposed 95% parsing target has not yet been measured |
| 2. Load a prepared local review CSV         | Built with bundled demonstration data; real RIC acquisition/provenance pending |
| 3. Detect and translate Chinese reviews     | Standalone preparation helper built; the app only reads prepared translations |
| 4. 1–10 difficulty score with fallback rule | Built; review input is a 1–5 numeric-rating proxy |
| 5. Multi-semester plan generator            | Built |
| 6. Review and adjust the plan               | Built |
| 7. Flag prerequisite conflicts              | Built for course-code prerequisites |

## Setup

Requires Python 3.10+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run the app

```bash
streamlit run src/course_planner/app.py
```

The app opens in your browser. Pick **Use the sample document** and press
**Build my plan** to see a draft plan straight away, then move courses between
semesters or add electives; every change is re-checked immediately. Uploaded
documents and their parsed results are kept in a local SQLite file
(`.course_planner/app.sqlite3`) and can be deleted from the sidebar. Set
`COURSE_PLANNER_DB` to store it somewhere else.

The difficulty score also reads prepared review rows from a local dataset
(`data/reviews/sample_reviews.csv`); set `COURSE_PLANNER_REVIEWS` to point at
your own prepared dataset. Without a dataset the score uses the requirement
document only.

## Reproducible sample

With the bundled requirement document, bundled demonstration review CSV and
default limits, **Build my plan** currently gives:

| Semester | Courses |
| -------- | ------- |
| 1 | COMP1117, MATH1013 |
| 2 | COMP2113, COMP2119, STAT2601 |
| 3 | COMP3230, COMP3314 |

The run parses 7 courses without warnings, loads 20 usable demonstration review
rows covering all 7 courses, and reports no unscheduled courses or plan issues.
Changing completed courses, semester limits or `COURSE_PLANNER_REVIEWS` can
change the result.

## Review dataset

The bundled `data/reviews/sample_reviews.csv` is demonstration data and is not
claimed to be real RIC data. A custom CSV uses these columns:

```text
course_code,text,rating,translation
```

- `course_code`, `text` and `rating` are required for a row to contribute.
- The current rating scale is 1 (lowest) to 5 (highest). It is mapped to a
  difficulty proxy; the app does not perform sentiment analysis on review text.
- An English review can leave `translation` blank. A Chinese review needs a
  prepared English `translation`; otherwise it is excluded from the score.
- The app reports how many rows were loaded and how many were excluded. A course
  without usable reviews falls back to credits and assessment count, rescaled
  equally across the full 1–10 range.

Before adding real review data, the team must confirm collection and reuse are
permitted, remove personal identifiers, and avoid committing account details or
other private information.

## Preparing the review dataset (team only)

**You do not need this section to use the app.** The app never translates
anything itself: it reads a review dataset that already contains English text,
so it needs no model, no extra install and no API key.

Chinese reviews can be translated once, by the team, when the dataset is built:

1. Install the optional translation dependencies and download the
   `Helsinki-NLP/opus-mt-zh-en` model. Installation and the first model download
   require internet access; translation then runs locally. PyTorch and the model
   can require hundreds of MB to a few GB:

   ```bash
   pip install -e ".[translation]"
   python -m course_planner.translation download
   python -m course_planner.translation translate "這門課功課很多"   # quick test
   ```

   The CLI command above is a quick text check, not a CSV batch-import command.
   The app itself never invokes the translator.

2. Have a Chinese-reading teammate spot-check the output.
   `export_review_sample` writes a CSV of random translated reviews with blank
   `adequate` and `notes` columns to fill in. Machine translation can miss tone
   and idioms, and the model is weaker on colloquial Cantonese.
3. Ship the checked dataset with both the original and the English text, so any
   score can be traced back to its source.

Reviews that are still untranslated when the app loads them are left out of the
difficulty score, and the app says so.

## Data and privacy

The running app does not send requirement documents or review data to a remote
service. Successfully parsed inputs and their parsed JSON are stored in the
local SQLite file `.course_planner/app.sqlite3`; the sidebar can delete its saved
rows. Package installation and the optional first translation-model download do
use the internet.

## Development

```bash
python -m pytest -q       # run the complete test suite, including Streamlit UI tests
python -m pytest -q --ignore=tests/test_app.py  # run the non-UI suite only
python -m ruff check .    # lint
```

Check the plan generator against a folder of requirement documents (every plan
must contain each course once, respect prerequisites and stay under the load
limit, and be more even than document order in at least 4 of 5 cases):

```bash
python -m course_planner.evaluation tests/fixtures/requirements
```

For the five bundled constructed fixtures, the current result is 5/5 legality
checks, 4/5 plans more even than document-order baseline, and overall `PASS`.
This evaluation uses document-only difficulty scores; it does not validate the
review dataset. In the supplied archive, 232 non-UI tests passed on 26 October
2026. The full Streamlit UI suite should also be run in the project environment
before submission.

## Known limitations

- The proposed 95% parsing target has not been measured on a labelled corpus.
- The bundled reviews are demonstration data; real RIC acquisition, permission,
  provenance and evaluation are pending.
- Review influence is derived from a numeric 1–5 rating, not review-text
  sentiment analysis. Translation quality has not been evaluated on real RIC
  or colloquial Cantonese data.
- Prerequisite checking recognises course codes. Conditions such as year
  standing, department approval and other non-code rules are not enforced.
- Semester availability, timetable clashes, double majors, transfer credits and
  requirement waivers are outside the current scope.
- This is a planning aid, not an official HKU graduation audit or difficulty
  rating; students must verify the result with current programme rules and an
  academic adviser.
