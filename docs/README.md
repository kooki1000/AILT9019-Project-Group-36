# Project webpage

`index.html` is the project page for AILT9019 Group 36. It is plain HTML, CSS and JavaScript with no build step.
Publish it with GitHub Pages: Settings > Pages > Deploy from a branch > `main` / `/docs`.

- `plan-data.js` holds the real runs shown in the page's interactive plan and is generated, not hand-edited.
  Regenerate it after changing the parser, scoring or planner: `python docs/build_plan_data.py`.
- `assets/` holds screenshots of the running app.
- To embed the recorded demo, set `VIDEO_ID` near the end of `index.html` to an unlisted YouTube video id.
- The evidence chart's numbers come from `python -m course_planner.evaluation tests/fixtures/requirements`.
