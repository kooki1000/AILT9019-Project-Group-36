# AILT9019 Project – Group 36: HKU Course Planner

HKU publishes what each programme requires, but not when to take it or how heavy a
semester will feel. Students usually work that out from memory, a spreadsheet or a short
chat with an adviser, and it is easy to find out a semester is overloaded only after
enrolling. The HKU Rights and Interests Committee (RIC) website has first-hand reviews of
how hard courses feel, but we couldn't find a tool that connects those reviews to an actual
plan.

This app reads a programme's requirement document (the faculty's syllabus PDF, pasted
text or a CSV), works out which courses are still needed and in what order they can be
taken, scores how hard each course is, and spreads them over semesters so no semester
carries far more than the others. You can then move courses around, add electives and rate
courses yourself, and every change is checked straight away.

It is a draft-plan helper for students who already know their programme. It is not a
graduation audit, it does not replace an academic adviser, and it leaves out double majors,
transfer credit and requirement waivers. Everything runs on your own computer. Nothing you
upload is sent anywhere unless you turn on the optional AI-assisted parsing (see below).

This repository is Group 36's project for AILT9019 AI Literacy II. A short project page,
with an interactive 8-semester plan, lives in [`docs/`](docs/README.md) and is published at
<https://kooki1000.github.io/AILT9019-Project-Group-36/>.

## Contents

- [Quick start](#quick-start)
- [Using the app](#using-the-app)
- [How the plan and the difficulty score work](#how-the-plan-and-the-difficulty-score-work)
- [Reading faculty syllabuses](#reading-faculty-syllabuses)
- [AI-assisted parsing](#ai-assisted-parsing-optional)
- [Review data](#review-data)
- [Where your data goes](#where-your-data-goes)
- [Development and testing](#development-and-testing)
- [Parser as an agent skill](#parser-as-an-agent-skill-claude-and-chatgpt)
- [Status and known limitations](#status-and-known-limitations)
- [Team and AI use](#team-and-ai-use)

## Quick start

You need Python 3.10 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
streamlit run src/course_planner/app.py
```

The app opens in your browser. Leave **Use the sample document** selected and press
**Build my plan**. The sample is a short, fictional Computer Science programme, so you get a
draft plan without uploading anything:

| Semester | Courses |
| -------- | ------- |
| 1 | COMP1117, MATH1013 |
| 2 | COMP2113, COMP2119 |
| 3 | COMP3230, COMP3314, STAT2601 |

That run reads 7 courses with no warnings, uses 48 student reviews that cover all 7,
and finds nothing unscheduled and no plan problems. The difficulty spread (the variance of
the semester totals) is 7.26 for this plan against 13.48 for taking the courses in document
order. Reviews visibly move scores: STAT2601 goes from 5.50 (document only) to 6.17, and
COMP3314 drops to 4.66. Changing the completed courses, the semester limits or the review
file can change the result.

For something closer to a real degree, `data/samples/cs_route_8_semesters.txt` is a route
built from the HKU 2025-26 BEng (Computer Science) syllabus and its mock study plan. The
app reads its 26 courses that have a course code. The interactive board on the project page
goes further: `docs/build_plan_data.py` adds the Common Core, Chinese language and free
elective slots (which have no code), splits the year-long final year project across Year 4,
and plans all 240 credits over 8 semesters.

## Using the app

### 1. Give it your requirement document

Upload a PDF, plain text or CSV file, or paste
the text. Anything else is refused with a message saying so. Two optional boxes help when
the document is not a simple list:

- *Courses you have already completed* are left out of the plan and count as done for
  prerequisites.
- *Only plan these courses* is for documents that list far more than one student takes,
  such as a faculty catalogue. Type the codes you plan to take and only those are planned.

If the file contains several degrees (say, one syllabus each for Computer, Electrical and
Electronic Engineering), a **Programme in this document** menu appears after the first
build. The first degree is read by default. Pick another and press **Build my plan** again.

The sidebar sets the limits: credits per semester (24 by default), courses per semester (5)
and the number of semesters (8). It also has the button that deletes your saved documents.

### 2. Read the draft plan

Each semester shows its courses, credits and total difficulty,
with a note on how each score was reached ("Document only (no reviews)", "Past student
reviews (4)" or "Your own rating"). Problems are listed in words with an icon, never by
colour alone. If a course cannot be scheduled the app says which one and why, for example a
circular prerequisite, a prerequisite that is not in the document, or a course bigger than
the semester limit. It never drops a course quietly or hands back an invalid plan.

A line under the plan compares how evenly your semesters are loaded with taking the courses
in the order the document lists them. The **Student reviews behind each score** panel lists
the reviews used, with the original wording next to the English text.

### 3. Adjust it

Under *Adjust your plan* you can move a course to another semester or a
new one, add an elective, give a course your own difficulty rating (it replaces the
estimate), and reset to the suggested plan. The app never refuses a move. It re-checks
prerequisites and load after every change and shows the problems, so you can try something
and see what it breaks. **Download plan as CSV** saves the current plan, including your
edits.

### Electives

Syllabuses contain elective lists and "choose one of" options, and a student takes only
some of them. So the app plans the required courses and tells you how many it left out. To
bring one in, add it under *Add an elective* by its code. If the document describes it, its
title, credits and prerequisites are filled in for you.

## How the plan and the difficulty score work

### The difficulty score

Each course gets a number from 1 (light) to 10 (heavy) from three inputs:

| Input | Weight | How it is turned into a 0 to 1 value |
| ----- | ------ | ------------------------------------ |
| Credits | 35% | credits divided by 12, capped at 1 |
| Graded assessments | 35% | number of assessments divided by 8, capped at 1 |
| Student reviews | 30% | the review ratings, described below |

The weighted sum is stretched onto the 1 to 10 range. If a course has no usable reviews,
the score uses only credits and assessments, their weights rescaled so the result still
spans 1 to 10, and the course is marked as review-free. If the document does not give
credits or an assessment count, the score assumes 6 credits and 4 assessments and says so.

Reviews enter through their 1 to 5 rating: 5 counts as easy and 1 as hard. The ratings for
a course are combined with a trimmed mean (the lowest and highest fifth are dropped once
there are five or more), so one extreme review neither decides the score nor gets thrown
away. The app does not read the review text. It keeps the text next to each score only so
you can check where a number came from.

The score is a rough estimate built from past student reviews and what the document says.
It is not an official HKU rating.

### The plan

The planner first checks which courses can ever be scheduled. Then it orders them by
prerequisites and finds the fewest semesters that fit your limits. Within that length it
moves courses around to even out the total difficulty per semester, measured as the
variance of the semester totals. The comparison line in the app is that variance against
the same courses taken in document order.

## Reading faculty syllabuses

Real syllabuses differ a lot between faculties, so the parser handles several layouts, even
mixed in one file:

- labelled blocks: `COMP1117 Programming (6 credits)` followed by `Prerequisite:` and
  `Assessment:` lines;
- table rows: `COMP1117 Computer programming 6`, with or without a year-of-study column;
- course descriptions: `COMP1117. Computer programming (6 credits)`, some prose, then the
  `Prerequisite:` and `Assessment:` lines;
- plain course lists under headings such as "Core courses" or "Disciplinary Electives".

### What the parser decides, and how it says so

- **Required or choice.** Courses in elective lists, "choose one of" groups and "Focus"
  lists are tagged as electives. So are courses that are only described in a document that
  also has requirement tables.
- **Several degrees in one file.** Each degree's tables are kept apart and one is read at
  a time. Course descriptions that follow are shared. Tables after a `MAJOR IN` or `MINOR IN`
  heading are ignored.
- **Too many courses.** A document with more than 60 required courses and no list from you,
  like the BA catalogue, is not planned. The app asks for your course list instead.
- **Prerequisites.** Brackets and precedence are respected, so `ELEC2543 or (COMP2119 and
  COMP2396)` becomes the equivalent AND-of-OR form that the planner uses. The "and" inside a
  course title does not split a requirement. "Take X concurrently", a grade on a course,
  `Mutually exclusive with` and placeholder codes like `XXXX2002` are not prerequisites.
- **Things that cannot be checked.** A prerequisite written as an exam level or approval
  ("Level 2 in HKDSE Mathematics, or MATH1011", "special approval") cannot be enforced, so
  it is reported as a warning. The parser never drops one silently. A course with no credits
  in the document is also warned about, and its credits are left empty rather than guessed.
- **Assessments** written as percentages (`50% coursework, 50% examination`) count as two.

### Documents we have tried

We tried it on eleven real 2025-26 and 2026-27 documents: BEcon, BEng (CompSc), BEng (DASE),
BEng (CE, EE and ElecE), BA, BJ, BJ (MAI), BSocSc, LLB, BA & LLB, and the ENGG regulations.
That last file is rules with no course list; the app recognises it and asks for the syllabus
instead. None of these has hand-made labels, so we give no accuracy figure for them. We read
the `syllabus_report` output against the PDF text and fixed what was wrong.

### Trying another syllabus

This reports how a file was read, locally, and stores nothing:

```bash
python -m course_planner.syllabus_report path/to/syllabus.pdf
python -m course_planner.syllabus_report path/to/folder --all
python -m course_planner.syllabus_report file.pdf --programme "ELECTRICAL ENGINEERING"
```

It prints how many courses it found (required and elective), how many have credits,
prerequisites and assessments, the parser's warnings, a "CHECK THESE" list for the usual
signs of trouble (no courses, many without credits, titles as long as paragraphs), and a
sample to compare against the PDF. A clean report is not proof, so look at a few courses
yourself, then upload the same file in the app.

## AI-assisted parsing (optional)

The built-in parser is deterministic and offline. For documents it struggles
with, turn on **Ask an AI to help read messy documents** in the sidebar. The
document text is then sent to Alibaba Cloud (Bailian) once per build, and the
app adds any courses the AI finds that the built-in parser missed. At most 100,000
characters are read. Everything else still works without it. We have not looked into
Alibaba Cloud's retention terms, so don't send a confidential document without permission.

```bash
export COURSE_PLANNER_API_KEY=...    # required (DASHSCOPE_API_KEY also works)
export COURSE_PLANNER_API_MODEL=qwen-plus  # optional; the default
```

The answer is treated as a suggestion, not as truth:

- a course is kept only when its code looks like a course code and appears in
  the document text itself, so an invented course cannot reach the plan;
- courses the built-in parser already found are never replaced, and its
  warnings still apply;
- everything the AI adds, ignores or fails at is reported in words, and the
  app runs exactly as usual with the toggle off or without a key.

A real course code can still come back with the wrong credits or prerequisites, so check
anything the AI added against your document. The tests use a mocked AI; no live Bailian
request has been part of our checks.

Successful AI answers are cached locally, keyed by the document's bytes, so
the feature keeps working for a document even after the key expires or the
network is gone: the app replays the saved answer and says plainly that it is
doing so. The cache lives in the same SQLite file as your saved documents and
is wiped by the same delete button.

## Review data

### File format

The app reads reviews from one local CSV, `data/reviews/sample_reviews.csv` by default. That
file holds 48 real reviews of seven courses (COMP1117, COMP2113, COMP2119, MATH1013,
STAT2601, COMP3230 and COMP3314) taken from RIC (<https://richku.com/courses>), with no
usernames, account details or teacher names. The 1-5 ratings are ours, assigned during
dataset preparation (1 = hardest, 5 = easiest), not RIC's.
Set `COURSE_PLANNER_REVIEWS` to use a different file. Without any file, scores come from the
document alone.

```text
course_code,text,rating,translation
```

- `course_code`, `text` and `rating` are needed for a row to count.
- The rating runs from 1 (lowest) to 5 (highest). A rating outside that range, such as 0 or
  8 on a 1 to 10 scale, is left out of the score and counted as excluded. It is never
  stretched into the hardest or easiest review.
- An English review can leave `translation` blank. A Chinese review needs an English
  `translation` already filled in, otherwise it is left out.
- After a build, the app says how many reviews it loaded and how many it left out.

### Adding more reviews

The bundled reviews were collected from RIC for this project, with no usernames, account
details or other private information, and teacher names removed. Someone could still search
RIC for a quoted sentence. RIC's published rules (<https://richku.com/logs>) say how students
earn access to its course planner, but not whether review text may be copied or
redistributed, and we have no written permission. That is an open gap. If you add more
reviews, keep the same rules, and have a teammate spot-check the ratings and translations.

### Preparing a translated dataset (team only)

You do not need this to run the app, which never translates anything and needs no model or
API key. Chinese reviews can be translated once, when the dataset is built:

1. Install the optional dependencies and download the `Helsinki-NLP/opus-mt-zh-en` model.
   This needs internet and can take from hundreds of MB to a few GB. Translation then runs
   locally.

   ```bash
   pip install -e ".[translation]"
   python -m course_planner.translation download
   python -m course_planner.translation translate "這門課功課很多"
   ```

   The last command is a quick check on one sentence, not a way to translate a CSV.
2. Have a teammate who reads Chinese check a sample. `export_review_sample` writes random
   translated reviews to a CSV with blank `adequate` and `notes` columns to fill in. Machine
   translation misses tone and idioms, and the model is weaker on colloquial Cantonese.
3. Keep both the original and the English text in the final file, so every score can be
   traced back to its source.

## Where your data goes

Nothing is sent to a remote service unless you turn on AI-assisted parsing
(see above), and then only the document text goes to Alibaba Cloud (Bailian),
once per build. Documents you upload, what the parser read from them and any
cached AI answers are saved in a local SQLite file,
`.course_planner/app.sqlite3` (change it with
`COURSE_PLANNER_DB`). The sidebar button deletes everything in it. If reading a file fails,
for example in a live demo, the saved result for the same file is shown instead, and the app
says so. The review CSV is a plain file next to the app, is never copied into the database,
and is not touched by that button. Only installing the packages and the one-off translation
model download use the internet.

## Development and testing

### Running the tests

On 18 November we ran everything below from the project archive in a fresh Linux
environment (Python 3.12.14): 392 tests passed and 1 was skipped (the real-syllabus test,
which needs a folder of PDFs). Ruff passed, the app started, and both parsing evaluations
and the planning evaluation passed. That was not a fresh clone from GitHub.

```bash
python -m pytest -q                              # everything, including the Streamlit tests
python -m pytest -q --ignore=tests/test_app.py   # without the browser-style app tests
python -m ruff check .                           # lint
```

### Plan check

This runs the proposal's test on a folder of requirement documents. Every
plan must contain each required course once, respect prerequisites and stay within the load
limit, and be more even than document order in at least 4 of 5 cases:

```bash
python -m course_planner.evaluation tests/fixtures/requirements
```

On the five constructed fixtures it gives 5 of 5 legal plans and 4 of 5 more even than the
baseline, so it passes, but only just: the 6-course minor comes out no more even than
document order (0.07 against 0.07), because there is almost nothing to balance. It uses
document-only scores and says nothing about the reviews.

### Parsing check

The proposal counts parsing as done when at least 95% of courses and
prerequisite links are extracted correctly. Each document in `tests/fixtures/labels/` has a
hand-written label file with its courses, credits, assessment counts and prerequisite
groups, and the checker compares the parser against it:

```bash
python -m course_planner.parsing_eval tests/fixtures/labels \
    tests/fixtures/requirements tests/fixtures/messy data/samples
python -m course_planner.parsing_eval tests/fixtures/labels_syllabi tests/fixtures/syllabi
```

A *link* is one prerequisite group of one course, so `COMP1117 and (MATH1013 or MATH1853)`
is two links, and a half-right "or" group counts as wrong. Recall and precision must both
reach 95% for courses and for links. Credits and assessment counts are reported but are not
part of the bar. Both commands pass at 100%. The first set covers the five plan fixtures,
the sample and two harder layouts. The second covers fictional documents built to follow the
structure of the real syllabuses. The tests also push the text documents through the PDF
path.

### Real syllabuses

The figures above are for documents we wrote, so they show the parser handles those layouts,
not how well it does on any real faculty file. For real files there are no labels. Instead,
`tests/test_real_syllabi.py` checks that nothing looks wrong (no paragraph read as a title,
no course missing a warning for missing credits, no duplicate or placeholder codes). It
runs only when you point it at a folder of PDFs, which should hold syllabuses and nothing
else:

```bash
COURSE_PLANNER_REAL_SYLLABI=path/to/folder python -m pytest tests/test_real_syllabi.py
```

## Parser as an agent skill (Claude and ChatGPT)

`skills/parse-requirements/` packages the parser in the open Agent Skills format: a
`SKILL.md` with a name and description, plus a `scripts/` folder. Both Claude and
ChatGPT/Codex document this layout. It prints courses, prerequisites and warnings as JSON.

```bash
python skills/build_skill.py        # writes dist/parse-requirements.zip
```

The zip carries its own copy of the parser modules, so nothing needs installing.

- **Claude:** upload the zip under Customize > Skills on claude.ai (this needs a paid plan
  with code execution), or unzip the folder into `~/.claude/skills/` for Claude Code.
- **ChatGPT and Codex:** the folder follows OpenAI's documented skill layout, but OpenAI's
  public docs don't say how to upload a zip or whether ChatGPT can run the scripts, so we
  have not tried it there.
- Plain text and CSV need no packages. PDF needs `pdfplumber` in the sandbox, which we have
  not confirmed is available in either product.

## Status and known limitations

### Proposal items

Must-have items from the proposal. All seven are built, with one change: Chinese reviews are
translated once while the review file is prepared, and the app reads only the stored English
text.

| Item | Status |
| ---- | ------ |
| 1. Parse a requirement document | Built. 100% recall and precision on our labelled documents. Tried on eleven real syllabuses and checked against their text, but with no labelled accuracy figure for real files. |
| 2. Load a local review CSV | Built, with 48 real RIC reviews of seven courses (ratings assigned by us during preparation). |
| 3. Detect and translate Chinese reviews | The translation helper is built. The app reads only translations prepared beforehand. |
| 4. 1 to 10 score with a fallback rule | Built. Review input is the 1 to 5 rating. |
| 5. Multi-semester plan | Built |
| 6. Review and adjust the plan | Built |
| 7. Flag prerequisite conflicts | Built for course-code prerequisites. Other conditions are reported, not enforced. |

Should-have items: CSV export, self-reported difficulty ratings and the skill file are
built (we had cut the skill file at the mid-term and added it back later). The optional
AI-assisted parse was not in the proposal and was added afterwards. A second review source
and the study with 3 to 5 HKU students were not done, and neither was the labelled test on
two real anonymised documents the proposal planned. We ran the parser on eleven real
syllabuses without labels instead.

### Known limitations

What to keep in mind when reading a plan:

- Syllabuses mostly don't list prerequisites. BEcon lists none, and BEng lists them only
  in course descriptions. BEcon's year-of-study column is read but not used, so a plan can
  put a final-year course in semester 1. Treat the order as a starting point.
- Documents that bundle degrees or long options groups (BA & LLB, BA, BSocSc) can't be
  planned without your help. BA & LLB has an options group without a heading the parser can
  read as "choose from", so some options count as required, and the app lists the ones it
  can't schedule.
- Several faculties leave credits out of whole lists. The app warns and leaves the credits
  empty. Stacked "A or B" table cells that PDF extraction scrambles can do the same.
- The score comes from a 1 to 5 rating, not from reading review text. The ratings are ours,
  from 48 reviews of seven courses. Not every Chinese translation has been read by a second
  person, and machine translation is weaker on colloquial Cantonese. A small set of reviews
  with ratings we assigned ourselves can bias the score. Showing the text next to each number
  lets you see the basis, but it doesn't remove the bias.
- Passing tests on documents we wrote says little about unseen faculty PDFs, and we haven't
  shown that the score really measures difficulty.
- AI-assisted parsing (optional, off by default) sends the document text to Alibaba Cloud.
  Its suggestions are checked against the document text, but check any added course yourself.
  This breaks the proposal's promise that nothing leaves your machine, which now holds only
  by default.
- Dependency versions are not pinned, and we did not record the exact versions of the
  development models or the revision of the translation model.
- Prerequisite checks cover course codes. Year standing, department approval and exam
  grades are not enforced.
- Semester availability, timetable clashes, double majors, transfer credit and requirement
  waivers are out of scope.

This is a planning aid. It is not an official HKU graduation audit or difficulty rating, so
check the result against the current programme rules and with an academic adviser.

Next, we would build an independently labelled set of real syllabuses, get a second reader on
the ratings and translations, add more option-layout fixtures and parse choice groups
explicitly, and pin dependency versions.

## Team and AI use

- **Ukai Koki:** parser, difficulty score, planner, Streamlit app, evaluation checks, tests
  and the public webpage.
- **Jiang Hongyi:** collected the RIC reviews and prepared the translations and ratings with
  Zhang Shui, and packaged the parser as a skill file.
- **Chen Muk Sing:** tested the interface, wrote the CSV cleaning scripts and filmed the demo
  video.
- **Zhang Shui:** collected and translated the reviews with Hongyi, built CSV export and the
  self-reported ratings, and edited the presentation video.

Tools used: Claude Code (Anthropic) wrote most of the code through pull requests. OpenAI
Codex drafted the README and ran the 18 November check. Alibaba Cloud Bailian
`qwen-plus` does the optional parsing, and Helsinki-NLP `opus-mt-zh-en` translated the Chinese
reviews once while the dataset was built. The full disclosure is in the group's final report.
