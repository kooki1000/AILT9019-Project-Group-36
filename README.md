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
| 1. Parse requirement document               | Built; 100% of courses and prerequisite links extracted on 8 constructed, hand-labelled documents (text, CSV and PDF paths); not yet tried on real public documents |
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

After building a plan, the **Student reviews behind each score** panel lists every
review for the planned courses: rating, original text, English translation and
whether it was used in the score, so any difficulty number can be traced back.

**Download plan as CSV** exports the current plan (including any manual edits and
electives) with semester, course, credits, difficulty and the basis of each score.

Under **Adjust your plan** you can also give a course your own 1-10 difficulty
rating. It replaces the estimate for that course (marked "Your own rating") and
the plan's totals and evenness are recalculated; you can remove it again.

### Faculty syllabuses

The parser reads three layouts, which can be mixed in one document: labelled blocks
(`COMP1117 Programming (6 credits)` then `Prerequisite:` / `Assessment:`), table rows
(`COMP1117 Computer programming 6`, optionally with a year-of-study column) and course
descriptions (`COMP1117. Computer programming (6 credits)` followed by prose and
`Prerequisite:` / `Assessment:` lines), and plain course lists (`CODE. Title (6 credits)` under
headings such as "Core courses" or "Disciplinary Electives", with or without descriptions later).
It was checked on eleven real 2025-26/2026-27 documents (BEcon, BEng(CompSc), BEng(DASE), BEng(CE, EE,
ElecE), BA, BJ, BJ(MAI), BSocSc, LLB, BA&LLB and the ENGG regulations), which differ a lot: see "Known limitations" for what still needs care. A regulations
document (rules but no course list) is recognised and the app says to upload the syllabus.

- **Required vs choice.** Elective lists, "choose one of" pairs, "Focus" lists and courses that
  appear only in a catalogue are tagged as electives. The app plans the required courses and
  says how many it left out; add an elective by its code (its details are filled in from the
  document) or list the courses you want under **Only plan these courses**.
- **Several degrees in one file.** Some documents hold one syllabus per degree (for example
  Computer, Electrical and Electronic Engineering, each starting with its title and `SYLLABUS`).
  The first degree is read by default, the app lists the others under **Programme in this
  document**, and choosing one and pressing **Build my plan** again plans that degree. Each
  degree's tables are kept apart; the shared course descriptions after them are used by all.
  Command line: `--programme "ELECTRICAL ENGINEERING"` with `syllabus_report` or `parse_cli`.
- **Several programmes in one file.** Tables after a `MAJOR IN ...` / `MINOR IN ...` heading are
  ignored. A document with more than 60 courses and no list from you (for example the BA
  catalogue) is not planned; the app asks for your course list instead.
- **Prerequisite expressions** are read with brackets and precedence: `ELEC2543 or (COMP2119 and
  COMP2396)` becomes the equivalent AND-of-OR form, the "and" inside a course title is not a
  connector, `, or` extends a list of alternatives, and "take X concurrently" or a grade on a
  course is not a prerequisite. An alternative that is an exam level ("Level 2 in HKDSE
  Mathematics, or MATH1011") makes the requirement impossible to enforce, so it is dropped and
  reported, unless one of its courses is in the document (then it is kept for ordering).
- **Prerequisites that are not course codes** ("At least one 2000-level course", "special
  approval") are reported as warnings instead of silently dropped. `Mutually exclusive with`,
  `Non-permissible combination` and placeholder codes such as `XXXX2002` are never prerequisites.
- Assessment percentages (`50% coursework, 50% examination`) are counted as two components.

**Trying another syllabus.** Run the report on any PDF, text or CSV file, or a whole folder
(it runs locally and stores nothing):

```bash
python -m course_planner.syllabus_report path/to/syllabus.pdf
python -m course_planner.syllabus_report path/to/folder --all     # list every course
```

It prints how many courses were found (required vs elective), how many have credits,
prerequisites and assessments, the parser warnings, anything that looks wrong ("CHECK THESE":
no courses, many courses without credits, paragraph-length titles) and a sample of courses
to compare with the PDF. Then upload the same file in the app to see the plan. For a pass/fail
version, `COURSE_PLANNER_REAL_SYLLABI=<folder> python -m pytest tests/test_real_syllabi.py`
(use a folder that contains only syllabuses).

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
- The current rating scale is 1 (lowest) to 5 (highest). A rating outside that range
  (for example 0, or 8 on a 1-10 scale) is left out of the score and counted as excluded; it is
  never clamped into the hardest or easiest review. It is mapped to a
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
review dataset. All 267 tests (including the Streamlit UI tests) pass.

### Parsing acceptance check

The proposal calls parsing done when at least 95% of courses and prerequisite
links are extracted correctly. Each document in `tests/fixtures/labels/` has a
hand-written JSON label file listing its courses, credits, assessment counts and
prerequisite groups; the check compares the parser's output with those labels:

```bash
python -m course_planner.parsing_eval tests/fixtures/labels \
    tests/fixtures/requirements tests/fixtures/messy data/samples
```

- A *link* is one prerequisite group of one course, so `COMP1117 and (MATH1013 or
  MATH1853)` is two links and a half-right "or" group counts as wrong.
- Both **recall** (how much of the truth was found) and **precision** (how much of
  what was found is true) must reach 95% for courses and for links.
- Credits and assessment counts are reported but are not part of the bar.
- Current result on the 8 documents (the five plan fixtures, the sample, and two
  harder constructed layouts: numbered/wrapped text and a CSV with different
  column names): 100% on all four measures, `PASS`. The test suite also runs the
  text documents through the PDF path.

Writing the harder documents found and fixed three real parser bugs: pipe-separated
one-line courses were read twice (inflating assessment counts and inventing extra
prerequisite groups), section headings such as "Core courses and electives" were
counted as assessments, and a CSV header like `Pre-requisites` was not recognised.

## Parser as an agent skill (Claude and ChatGPT)

`skills/parse-requirements/` packages the document parser in the open Agent Skills
format (`SKILL.md` with `name` and `description`, plus a `scripts/` folder), which both
Claude and ChatGPT/Codex document. It prints courses, prerequisites and warnings as JSON.

Build a self-contained upload (it bundles the parser modules, so nothing needs installing):

```bash
python skills/build_skill.py        # writes dist/parse-requirements.zip
```

- **Claude:** upload the zip under Customize > Skills on claude.ai (a paid plan with code
  execution is required), or unzip the folder into `~/.claude/skills/` for Claude Code.
  Claude requires the skill folder at the top level of the zip, which the builder does.
- **ChatGPT / Codex:** the same folder follows OpenAI's documented skill layout. OpenAI's
  public docs do not describe a zip upload or whether ChatGPT can run scripts, so this
  has **not been tested in ChatGPT**; if scripts cannot run there, the instructions still
  explain the output format.
- Plain text and CSV need no packages. PDF needs `pdfplumber` in the sandbox, which we
  have not confirmed is available in either product.

## Known limitations

- Real syllabuses mostly do not list prerequisites (BEcon lists none; BEng lists them only in
  course descriptions) and BEcon's year-of-study column is not used by the planner, so a plan
  can place a final-year course early. Treat the order as a starting point.
- Combined programmes (BA&LLB) list long options groups without a heading the parser can read as
  "choose from", so some options are treated as required; the app reports the ones it cannot
  schedule. Several faculties omit credits for whole lists (always warned, never guessed).
- Table layouts that pdf text extraction scrambles (for example BEcon's stacked "A or B" rows)
  can leave a course without credits; the app warns when that happens.
- The 95% parsing target is met only on constructed documents written by the team.
  The proposal's two real public requirement documents (identifying details
  removed) have not been added, so real-world parsing accuracy is still unmeasured.
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
