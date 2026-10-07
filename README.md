# JobHelper 🧭

A personal job-application assistant built from **5 cooperating agents**, powered
by **your Claude subscription** (via the Claude Code CLI — no paid API key, no
per-token billing).

> 📋 **All commands in one place:** see [COMMANDS.md](COMMANDS.md).

| # | Agent | What it does |
|---|-------|--------------|
| 1 | `agent1_cv` | Reads your CV (PDF/DOCX/TXT) and builds a target job profile + search queries |
| 2 | `agent2_search` | Searches jobs.cz + prace.cz + LinkedIn (Prague), filters to English + your level, incl. adjacent roles |
| 3 | `agent3_letters` | Scores each job, writes a cover letter, and a keyword-tailored CV (re-emphasising your real experience for ATS) |
| 4 | `agent4_tracker` | Builds the Excel tracking table (status colour-coded, best matches first) |
| 5 | `agent5_responses` | Reads inbox replies, classifies rejections/interviews/offers into a **SQLite database**, updates statuses, and reports rejection analytics |

## Requirements

- **Claude Code CLI, logged in** with your subscription. Run `claude auth login`
  once and sign in. **Do not set `ANTHROPIC_API_KEY`** — leaving it unset is
  what makes the app use your subscription instead of the paid API.
- Python 3.10+
- **Job search for Prague needs no API key** — the default source pulls from
  **jobs.cz + prace.cz + LinkedIn** (LinkedIn's public guest endpoint). It keeps
  only English ads and roles at your level, and includes adjacent roles you
  qualify for (e.g. IT support / QA for a junior dev). (For personal use;
  against the boards' ToS, and may need selector fixes if they change their HTML.
  Indeed & Glassdoor are excluded — they hard-block scraping.)
- (Optional) Other countries: an [Adzuna](https://developer.adzuna.com) key
  (`--source adzuna`, set `ADZUNA_COUNTRY`). Adzuna does **not** cover Czechia.
- (Optional) A Gmail **App Password** for email status sync.

## Setup

```bash
cd path/to/JobHelper          # wherever you put the project
python3 -m venv .venv
source .venv/bin/activate
pip install --require-hashes -r requirements.lock   # exact, hash-checked packages (or: pip install -r requirements.txt)

cp .env.example .env      # optional settings (the Gmail password does NOT go here)
```

Put your CV (English) in `data/cv/` — e.g. `data/cv/my_cv.pdf`.

## Use

### Desktop app (recommended)

A window where the 5 agents are robots on a factory conveyor belt — jobs ride
the belt and you drive everything with buttons (Run search, Scan email, browse
your leads/applications/responses, open letters & CVs, edit options).

```bash
python app_qt.py         # native Qt app (PySide6/QML — no web engine, GPU-rendered)
```

Click a job row to see it in full (description, why it got its score, keywords in
and not in your CV). Applications with no reply for 10 days get a follow-up
reminder with a draft email to copy. A running search or scan can be stopped. With
LibreOffice installed, each adapted CV and letter also gets a PDF copy.

In the same window you can put a date on a job (interview, deadline) and get a
reminder the day before, keep notes per company, paste in a reply that came outside
email, and compare the adapted CV with your master CV. Insights also lists what the
postings say they pay. Options can widen the email scan to archived mail and spam.

Everything in the window maps to the command-line tools below.

### Command line

```bash
# Full pipeline: analyze CV → search Prague → write letters → build Excel
python run.py

# Other cities / stricter matching / reuse the last CV analysis
python run.py --where Brno
python run.py --threshold 70
python run.py --reuse-profile

# Add remote English roles (RemoteOK + We Work Remotely) to a Prague run
python run.py --include-remote

# Pick a specific source
python run.py --source remote                   # remote-only (RemoteOK + WWR)
python run.py --source all                       # every source
python run.py --where Warsaw --source adzuna    # needs an Adzuna key + ADZUNA_COUNTRY=pl
```

Outputs:
- `data/excel_new_jobs/new_jobs.xlsx` and `data/excel_applications/applications.xlsx`
  — the tracking tables (best matches first, colour-coded status)
- `data/cover_letters/` — one cover letter (`.docx`) per job worth applying to
- `data/tailored_cvs/` — an adapted CV per strong match (re-emphasises
  your **real** experience to match the posting; never invents anything).
  Your master CV stays in `data/cv/`. Disable with `python run.py --no-tailor-cv`.
- `data/jobs.json` — the underlying database (encrypted)
- `data/profile.json` — Agent 1's CV analysis (encrypted)

### Tracking your applications (Agent 4)

```bash
python status.py list                          # see everything + IDs
python status.py update adzuna-123 applied     # mark one applied by hand
python status.py update adzuna-123 interview --note "call Fri 10:00"
python status.py sync                          # read inbox replies, auto-update
python status.py rebuild                       # regenerate the Excel file
```

`sync` opens your inbox **read-only** — it never sends, deletes, or marks
emails. It matches messages to jobs by company name and asks the model whether
each reply is an interview invite, rejection, offer, etc., then updates the
table **and** stores each response in the database (Agent 5).

### Rejection & response analytics (Agent 5)

```bash
python status.py responses          # response rate + rejection-reason breakdown
python status.py responses --scan   # scan inbox for new replies first, then report
```

This reads every application reply into `data/responses.db` (encrypted) and writes
`data/excel_reports/responses_report.xlsx` with a Summary sheet (response rate, rejection
reasons) and a Responses sheet (every reply). Use it to see *why* you're getting
rejected and adjust.

### Connecting Gmail (one-time)

1. Turn on **2-Step Verification** for the Google account (required for app passwords).
2. Go to **Google Account → Security → App passwords**, create one named "JobHelper".
3. In the app, click the **Account** chip, then **Change** on *Job email*, type the
   address and the 16-letter password and press **Save**. The address is saved to
   `.env`; the password goes to the macOS Keychain.
Never use your real Google password — only an App Password, which you can revoke
anytime. The app only ever **reads** your inbox.

The desktop app stores the app password in the macOS **Keychain** (enter it in the
**Account** card), and keeps your job data encrypted on disk. See the
*Security* section of [COMMANDS.md](COMMANDS.md).

## Security

- The Gmail app password and the data key are in the macOS **Keychain**.
- `jobs.json`, `profile.json`, `ui_settings.json`, `responses.db` and all backups are
  **AES-256 encrypted** on disk.
- The CV rules, letter rules, letter template, master CV and career-site list are
  **signed**; a change made outside the app must be approved before the next run.
- Packages are pinned by SHA-256 in `requirements.lock`.

**Save your recovery key once** (needed on a new Mac or after a Keychain reset):

```bash
python status.py security recovery-key
```

CVs, cover letters and Excel trackers stay normal files so Word and Excel can open
them; an encrypted drive is what protects those. Full details, including where to
find the Gmail password in Keychain Access and when to use *Approve*, are in
section 10 of [COMMANDS.md](COMMANDS.md).

## Using it with your own CV

Nothing about one particular person is built into the app.

1. Put your CV in `data/cv/` (or choose it in the Account card). A `.docx` whose sections are
   headed PROFILE and KEY SKILLS gets a fully adapted copy per job; other formats get a
   rewritten profile paragraph. Generated files are named after your CV file:
   `FirstnameLastname_CV_EN.docx` gives `FirstnameLastname_CV_<Company>_<Role>.docx` and
   `FirstnameLastname_CoverLetter_<Company>_<Role>.docx`.
2. In Options, fill in **About you** (right to work, when you can start), your city, your
   search roles and the words to skip. Turn **English only** off if you also want roles that
   require Czech.
3. Rules for the CV and the letter are optional. Without them the built-in general rules are
   used. To write your own, copy `data/cv_adaptation_instruction.example.md` and
   `data/cover_letter_instruction.example.md` to the same names without `.example` and edit
   them. `{{name}}`, `{{first_name}}`, `{{location}}`, `{{right_to_work}}` and `{{start}}` in
   those files are filled in by the app.
4. A letter template (`data/cover_letter_template.docx`) is optional too: with one, letters keep
   its head and layout; without one, a plain business letter is written with the name and
   contacts from your CV.

## English-only jobs

Because you don't speak Czech, Agent 2 keeps **only English-language ads** by
default (an English ad is a strong signal the role welcomes non-Czech speakers).
Czech-language listings are filtered out automatically. To include everything:

```bash
python run.py --all-languages
```

## Tests

```bash
source .venv/bin/activate
pytest
```

The suite runs offline (no network, no Claude usage): scraper parsing is tested
against saved HTML fixtures in `tests/fixtures/`, and the AI agents are tested
with the LLM mocked. In VS Code, tests also appear in the Testing panel.

It never touches your real data: every test works in a temporary folder, and the
`.env` file, the weekly LaunchAgent and the Claude CLI are stubbed. Besides the
agents and scrapers it covers the desktop app (the window is loaded offscreen:
welcome screen, progress bar, dialogs, input validation), the bridge between the
window and the agents, saved Options, the weekly schedule and `run.py`.
Every new feature gets tests in the same change.

## Open in VS Code

```bash
code path/to/JobHelper
```

Recommended extensions (Python + debugpy) are suggested automatically, and the
Run/Debug panel has ready-made launch configs for the pipeline and status tools.
Pick `.venv` as the interpreter when prompted.

## Claude usage tracking

Every model call's tokens and API-equivalent cost are tracked. `run.py` prints a
summary at the end, and you can check anytime:

```bash
python status.py usage          # tokens + API-equiv. cost, broken down by agent
python status.py usage --reset  # zero the counters
```

What the numbers mean: the app uses your Claude **subscription**, so there's no
dollar bill — usage counts against your normal Pro/Max limits. The tracker shows
**tokens used** and an **API-equivalent cost** (a proxy for "how much"), plus a
rate-limit snapshot when the SDK reports one. Your subscription's exact remaining
quota isn't exposed via the API — for that, run `/usage` inside the Claude Code
terminal. To keep usage low, the app makes **one focused model call per task**
(CV analysis, per-job scoring+letter, per-email classification), and the job
search itself uses **no** Claude usage.
