# JobHelper

A personal job-application assistant for macOS. Five cooperating agents find postings, score
them against your CV, write an adapted CV and a cover letter for the good ones, and keep track
of what you applied to and what the companies answered. It runs on **your Claude subscription**
through the Claude Code CLI: no paid API key, no per-token bill.

- **All commands with their options:** [COMMANDS.md](COMMANDS.md)
- **How to use each part, step by step, with pictures and reference tables:** [docs/GUIDE.md](docs/GUIDE.md), also as [docs/GUIDE.pdf](docs/GUIDE.pdf)
- **The rules it is built by, how the code is laid out, what is left to do:** [HANDBOOK.md](HANDBOOK.md)
- **What changed, day by day:** [CHANGELOG.md](CHANGELOG.md)

| # | Agent | What it does |
|---|-------|--------------|
| 1 | `agent1_cv` | Reads your CV (PDF, DOCX or TXT) and builds a profile and search queries |
| 2 | `agent2_search` | Searches the job boards, filters by language, level and age, and notes why each dropped posting was dropped |
| 3 | `agent3_letters` | Scores each posting, then writes an adapted CV and a cover letter for those above your limit |
| 4 | `agent4_tracker` | Builds the Excel tables (new jobs, applications) |
| 5 | `agent5_responses` | Reads replies in your mailbox, files them to applications, and reports why you get rejected |

## Requirements

- macOS.
- **Claude Code CLI, signed in** with your subscription (`claude auth login`). **Do not set
  `ANTHROPIC_API_KEY`**: leaving it unset is what makes the app use the subscription, and the
  app refuses to run a search while it is set.
- Python 3.10 or newer.
- Optional: a Gmail **App Password** for reading replies; LibreOffice for PDF copies of the
  documents; a Jooble or Adzuna key for those two sources.

Job search needs no key. The default sources are jobs.cz, prace.cz, LinkedIn's public pages and
the career sites of the companies you list; two remote boards can be added in Options. The boards are read for
personal use only, at a modest pace, and a site that turns programs away is left alone.

## Setup

```bash
cd path/to/JobHelper          # wherever you put the project
python3 -m venv .venv
source .venv/bin/activate
pip install --require-hashes -r requirements.lock   # exact, hash-checked packages (or: pip install -r requirements.txt)

cp .env.example .env          # optional settings (the Gmail password does NOT go here)
```

Put your CV in `data/cv/`, or choose it in the Account card when the app starts.

## Use

### The window

```bash
python app_qt.py
```

Five robots on an assembly line show what is running. **Run search** finds and scores new
postings; **Scan email** reads replies. The lists on the left hold new jobs, your applications
and every reply. Click a job to open its window.

What the window does for you:

- **Before you apply:** why the job got its score, which keywords of the posting are in your CV,
  a side-by-side view of the adapted CV and your master CV, an editor for the letter, drafted
  answers for that job's application form, the letter and CV as one PDF, and a short checklist.
- **After you apply:** status changes from the replies in your mailbox, a reminder to follow up
  after ten quiet days with a draft to copy, dates with notifications, notes per company, and
  an interview preparation you can edit and open as a Word sheet.
- **Keeping the list honest:** a score that rests on little text is marked and can be fixed by
  reading the posting again or pasting its text; a job can be scored again with your current
  Options; postings that closed are noticed; documents of a job that fell below your limit can
  be moved to a backup and put back.
- **Filtered out:** every posting a search dropped is listed with its reason, and most can be
  brought back.
- **Insights:** which search roles work, which skills the postings ask for that your CV does
  not show, what the postings pay, how long companies take to answer.

A weekly run can do the search and the email scan by itself (the **Weekly run** card).

### The command line

```bash
python run.py                    # the whole pipeline, with the city saved in Options
python run.py --where Brno       # another city
python run.py --threshold 70     # write documents only for stronger matches
python run.py --reuse-profile    # skip reading the CV again
python run.py --include-remote   # add the two remote boards

python status.py list            # everything, with ids
python status.py sync            # read replies and update statuses
python status.py responses       # reply and rejection analytics
python status.py usage           # Claude usage of this app
```

The rest is in [COMMANDS.md](COMMANDS.md).

### Where things are written

- `data/cover_letters/`, `data/tailored_cvs/`: the documents, as Word files (and PDF with
  LibreOffice). Your master CV stays in `data/cv/`, your own letters in `data/my_letters/`.
- `data/excel_new_jobs/`, `data/excel_applications/`, `data/excel_reports/`: the Excel tables.
- `data/jobs.json`, `data/profile.json`, `data/responses.db`: the app's own data, encrypted.
- `data/backups/`: encrypted backups, made before anything is changed in bulk.

### Connecting Gmail (once)

1. Turn on 2-Step Verification for the Google account.
2. Create an App Password named "JobHelper" (Google Account → Security → App passwords).
3. In the app, open the **Account** chip, press **Change** on *Job email*, enter the address and
   the 16-letter password, and save.

The address goes to `.env`; the password goes to the macOS Keychain. Use an App Password, never
your real Google password. The app only ever **reads** the mailbox: it does not send, delete
or mark anything.

## Security

- The Gmail app password and the data key are in the macOS **Keychain**.
- Job data, the profile, settings, the reply database and all backups are **AES-256 encrypted**
  on disk.
- The CV rules, letter rules, letter template, master CV and career-site list are **signed**; a
  change made outside the app must be approved before the next run.
- Packages are pinned by SHA-256 in `requirements.lock`.

**Save your recovery key once.** You need it on a new Mac or after a Keychain reset:

```bash
python status.py security recovery-key
```

CVs, letters and Excel files stay ordinary files so Word and Excel can open them; an encrypted
disk is what protects those. Details are in section 10 of [COMMANDS.md](COMMANDS.md).

## Using it with your own CV

Nothing about one particular person is built into the app.

1. Put your CV in `data/cv/`. A `.docx` whose sections are headed PROFILE and KEY SKILLS gets a
   fully adapted copy per job; other formats get a rewritten profile paragraph. Generated files
   are named after your CV file.
2. In Options, set your city, your search roles, the **kinds of role you want and do not want**,
   the level words to skip and the years of experience you accept, and fill in **About you**
   (right to work, when you can start).
3. Check the profession chips under *Kinds of role you want*: they show what the app takes as
   your profession, which decides what is skipped before scoring. Pick it yourself if the app
   read it wrong. Seventeen professions are known.
4. Rules for the CV and the letter are optional. To write your own, copy
   `data/cv_adaptation_instruction.example.md` and `data/cover_letter_instruction.example.md`
   to the same names without `.example` and edit them.
5. A letter template (`data/cover_letter_template.docx`) is optional too: with one, letters keep
   its head and layout; without one, a plain business letter is written.

Whatever the app writes for you claims only what is in your CV or in your own notes under
*More about your work* in Options.

## Language of the postings

By default only English-language postings are kept, on the view that an English ad is a role
that works in English. Turn **English only** off in Options (or use `--all-languages`) to keep
postings in other languages too. Separately, a posting that requires a language your CV does
not show at a working level is scored low, whatever language it is written in.

## Tests

```bash
pytest -q
```

About 1,200 tests, two minutes, offline. They never touch your real data, the Keychain or
`.env`, never ask Claude, never read a real job board, and never open a file or put anything in
the Trash: every test works in temporary folders with stand-ins. The window itself is loaded
offscreen and driven by the tests. Every change comes with tests in the same commit.

## Open in VS Code

```bash
code path/to/JobHelper
```

Recommended extensions and launch configurations are included. Pick `.venv` as the interpreter
when asked.

## Claude usage

Every model call is counted. `run.py` prints a summary and `python status.py usage` shows it at
any time: tokens used and what the same work would have cost through the paid API. The app
uses your subscription, so that figure is a measure, not a bill. To keep usage low the app
scores five postings per call, skips plainly unsuitable postings before scoring, and the search
itself uses no Claude at all.
