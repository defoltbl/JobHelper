# AGENTS.md

Instructions for AI coding agents that work in this repository. People start with the
[README](README.md); the full rules and the decisions behind them are in [HANDBOOK.md](HANDBOOK.md).

## The project

JobHelper is a macOS desktop app (Python 3.14, Qt Quick through PySide6) that finds job postings,
scores them against a CV, writes adapted CVs and cover letters, tracks replies from a read-only
mailbox, and fills in application forms in the person's browser. Every model call goes through the
Claude Code program on a Claude subscription. The widget is Swift (WidgetKit).

## Commands

```bash
pip install --require-hashes -r requirements.lock                 # packages, pinned by SHA-256
python app_qt.py                                                   # the window
python -m pyflakes jobhelper tests scripts app_qt.py run.py status.py
python -m pytest                                                   # about 2,100 tests on every core, offline, about 1 minute
python scripts/build_app.py                                        # dist/JobHelper.app, then its checks
python -m pytest tests/guide_shots.py -q -o addopts=""             # the user guide's pictures
python scripts/guide_pdf.py                                        # docs/GUIDE.pdf and docs/CODE.pdf
python scripts/push_check.py                                       # before every push (also the pre-push hook)
```

## Rules you must keep

- **Never set `ANTHROPIC_API_KEY`.** The app must use the subscription; it refuses to run while a
  paid key is set. Run commands with `env -u ANTHROPIC_API_KEY`.
- **Tests never touch real things:** not the data in `~/Library/Application Support/JobHelper`, the
  Keychain, Claude, a mailbox, a job board or a browser. `tests/conftest.py` fails the run if the
  real data changes. Do not run the tests while a script changes the real data.
- **Every change comes with tests**, then pyflakes and the whole suite. In window tests, wait for a
  state (`_until_open`, `_until_closed`, `_until_shown`, `_until_true`), never a fixed pause: CI on a slow Mac
  fails on pauses. The cleanup after each window test closes every window and ends a pretend run.
- **What the model writes is checked in plain code** against the master CV (`cv_tailor`,
  `cover_letter`, `form_answers`). Do not weaken these checks to make a test or a text pass.
- **The app never acts in the person's name:** the mailbox is read-only, and the assistant never
  presses Submit or Next and never fills a password.
- **No personal data in code, tests or docs.** Use invented people and companies. The owner is
  named only in the README's Author section and on the licence's Required Notice line.
- **One rule in one place.** When the search, a setting and the window depend on the same rule,
  they call one function or class (for example `job_sources.SourceChoice`).
- **Code style:** object-oriented where state and behaviour belong together (SOLID, composition);
  pure helpers stay functions. Match the comments and naming of the code around you.
- **Writing:** the user guide and the technical documentation use ASD-STE100 Simplified Technical
  English (tests check sentence length). Use the en dash "–", never the em dash "—", in prose.
- **Each visible change** gets a line in [CHANGELOG.md](CHANGELOG.md); a change the user guide
  shows also updates its text, its pictures and its PDF.
- **No Russian services:** no such mail provider, job board, API or host.

## Versions and releases

- Version numbers follow semantic versioning: a fix only is `1.0.1`, new features `1.1.0`, a change
  that breaks saved data or habits `2.0.0`. The number is `app_info.VERSION`.
- Never commit to `main`: each change is a branch and a pull request that merges only with green CI.
- A new push to a pull request cancels that pull request's older CI run (`concurrency` in
  `.github/workflows/tests.yml`); a run on `main` is never cancelled.
- Each pull request adds its lines to [CHANGELOG.md](CHANGELOG.md) under `## Unreleased`.
- To release, one pull request renames `## Unreleased` to `## X.Y.Z – <date>` and sets
  `app_info.VERSION`. After it is merged: `git tag -a vX.Y.Z -m "JobHelper X.Y.Z"` on that commit of
  `main`, push the tag, and `gh release create vX.Y.Z` with that version's changelog as its notes.
- Never attach the built `JobHelper.app` to a release: it contains Qt and the Claude Code program.

## Where things are

| Path | What it holds |
|---|---|
| `jobhelper/` | All the logic, no window code: the five agents, the assistant, storage, encryption |
| `jobhelper/ui_api.py`, `api_*.py` | The back end the window calls, a facade over services |
| `jobhelper/qt_bridge.py`, `bridge_*.py` | Slots and signals between the window and the back end |
| `ui_qt/` | The window, one QML file per dialog or part |
| `widget/` | The macOS widget (Swift) and the library that asks macOS to redraw it |
| `macos/` | Swift for the app's own notifications (`Notify.swift`), built into the app as a library |
| `tests/` | The tests; `guide_shots.py` takes the user guide's pictures |
| `scripts/` | Building and checking the app, the PDFs, the diagrams, the push check |
| `docs/` | [User guide](docs/GUIDE.md), [technical documentation](docs/CODE.md), [notes and limits](docs/NOTES.md) |
