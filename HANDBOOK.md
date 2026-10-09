# JobHelper handbook

What to remember about this project: how to use the app, the rules it is built by, how the
code is laid out, how a change is checked, what was decided and why, and what is left to do.

- Every command with its options is in [COMMANDS.md](COMMANDS.md).
- What changed, day by day, is in [CHANGELOG.md](CHANGELOG.md) (also in the app: Help → What changed).
- Setup from nothing is in [README.md](README.md).

Keep this file current: when a rule, a decision or the to-do list changes, change it here in
the same commit.

---

## 1. Using the app

Start it from the project folder with the virtual environment active:

```bash
python app_qt.py
```

### A normal week

1. **Run search.** The five robots work in order: read the CV, search the job boards, score
   each posting and write a CV and letter for the good ones, build the Excel files. New
   postings land in **New Jobs**, best score first.
2. **Open a job** (click its row). Read *Why this score*, check the adapted CV and the letter,
   tick the steps under *Before you apply*, apply on the company's site, press **Mark applied**.
3. **Scan email** now and then. Replies are read (never changed) and move your applications to
   interview, rejected or offer by themselves.
4. **Applications** shows where each one stands. A job with a date (interview, deadline)
   appears on the main screen and you get a notification before it.

The **Weekly run** card can do steps 1 and 3 once a week by itself.

### Things worth knowing

| You want to | Where |
|---|---|
| Say which roles you want and do not want | Options → *Kinds of role you want / do not want* |
| Set or check what the app takes as your profession | Options → the chips under *Kinds of role you want* |
| Change the score from which letters are written | Options → *Write letters above* |
| See why a posting never reached the list | Main screen → *Filtered out* (with **bring back**) |
| Score a job again with today's Options | Job window → **Score again**; New Jobs → **Score all again** |
| Fix a posting the app could not read | Job window → **Read it again**, or **Paste the posting's text** |
| Put away documents of a job that fell below your limit | Job window or New Jobs → **Move … to backup**; **Put them back** undoes it |
| Draft answers for one job's application form | Job window → **Form answers** |
| Prepare for an interview | Application window → **Interview preparation** (editable, opens as a Word sheet) |
| Add a reply that did not come by email | Application window → **Paste a reply** |
| Use a letter you wrote yourself | Options → *Your own letters* → **Open folder** |
| Save the key you need on a new Mac | `python status.py security recovery-key` (do this once) |

### What the marks mean

- **strong / moderate / stretch**: the score band. **skipped**: the app saw from the title that
  it is another profession, another language or a far higher level, and spent no Claude call
  on it; **Score it anyway** overrides that.
- **scored from the title only / from a short summary**: the posting's text could not be read
  in full, so the score rests on little. A title-only score is capped at 40 and gets no documents.
- **was 55**: the score before the job was scored again.
- **documents from a higher score**: the letter and CV were written when the job scored above
  your limit; it is now below it.

---

## 2. Rules the app is built by

These came from decisions made while building it. A change that breaks one is a bug.

**Claude and accounts**
- The app runs on the Claude **subscription** through the Claude Code CLI, never the paid API.
  `ANTHROPIC_API_KEY` must stay unset; the app refuses to run a search with it set.
- The mailbox is opened **read-only**. Nothing is ever sent, deleted or marked.
- Secrets (the Gmail app password, the data key) live in the macOS Keychain and are never
  printed, logged or put in an error message. An address in an error loses its query part.

**What is written for the user**
- A CV, a letter, a form answer or an interview story never claims anything that is not in the
  master CV or in the user's own *More about your work* notes.
- A letter the user wrote themselves is never rewritten, replaced or moved. Only documents the
  app wrote can be.
- Texts use an en dash, not an em dash, no emojis, first person.

**Data**
- Before data is changed in bulk, a backup is made. Files are moved, not deleted: documents go
  to an encrypted backup folder, old copies go to the Trash.
- Job data, the profile, settings, the reply database and all backups are encrypted on disk.
- Nothing about one particular person is in the code, the tests or the docs, and no path of one
  machine. The app must work for anyone's CV.

**The window**
- Every place where text can be typed or pasted checks it and says what is wrong in red, next to
  where the user is looking: empty, wrong shape, too long (the limit is shown while typing;
  nothing is cut silently). The backend refuses the same things with the same reason.
- An action that replaces or throws away work asks once. Esc and ✕ never lose edits unasked.
- An action that must not run during a search or scan says so instead of doing nothing.
- Text wraps. It is not cut off.
- Both themes keep small text at a contrast of 4.5:1 or more (there is a test).

**Working on the code**
- Local git only. One commit per finished step, after the tests pass, with a short plain
  message. A line in `CHANGELOG.md` for every change the user can see.
- Tests come with the change, in the same commit, and a bug check follows every batch (section 4).

---

## 3. How the code is laid out

```
app_qt.py            starts the window
run.py               the same pipeline from the command line (used by the weekly run)
status.py            command-line tools: list, sync, security, usage …
jobhelper/           the logic (no window code)
ui_qt/               the window (QML), one file per dialog plus shared blocks
tests/               everything runs offline, in temporary folders
data/                your data; only the *.example.* files are in git
```

### The five agents

| Module | Does |
|---|---|
| `agent1_cv` | reads the CV, builds the profile and the search queries |
| `agent2_search` | searches the boards, filters, notes why a posting was dropped, second read of empty postings |
| `agent3_letters` | scores (five postings per call), caps, writes the CV and letter |
| `agent4_tracker` | builds the Excel files |
| `agent5_responses` | reads replies, files them to applications, analytics |

### Around them

- **Reading postings:** `scrapers_cz` (jobs.cz, prace.cz, company-branded pages), `scrapers_intl`
  (LinkedIn guest pages), `scrapers_remote`, `scrapers_ats` (company career systems),
  `scrapers_page` (any other page: only the copy it publishes for search engines).
- **Rules without a model call:** `filters` (level, years, languages), `prefilter` (another
  profession, unwanted roles), `keywords`, `salary`, `merge`, `followup`, `planner`.
- **Writing:** `cv_tailor`, `cover_letter`, `letters` (your own letters), `form_answers`,
  `interview_prep`, `prep_doc`, `pdf`.
- **Keeping data safe:** `vault` (encryption, backups), `integrity` (signed rule files),
  `housekeeping` (old backups, logs, the Trash), `store` and `db` (jobs and replies).
- **Claude:** `llm` (every call goes through it; pauses at the limit), `usage`.
- **The window's back end:** `ui_api` (what the window can ask for) and `qt_bridge` (the Qt
  side: slots, background work, progress).

### Things that are easy to get wrong

- **A running search holds its own copy of the jobs** and saves it when it ends. A hand edit
  must reach that copy too, or it is lost. `Api._change(job_id, fn)` does this by calling `fn`
  a second time on the search's copy, so **`fn` must give the same result when called twice**.
  If it moves files, it has to remember what it did the first time (see `shelve_docs`).
- **Background work answers through a signal** (`Bridge._post`), never by touching the window
  from a worker thread.
- **QML names:** a dialog in its own file reaches `theme`, `win`, `bridge` and the other
  dialogs through the context. A property named like `onSomething` is read as an event
  handler and silently does nothing. A component with its own `theme` property hides the
  global one: use `win.appTheme`.
- **Colours fade to `win.clearOf(colour)`**, not to plain transparent, or a dark shadow flashes.
- **A label on the orange or the green** takes `theme.accentInk`, which is white in the light
  theme and dark in the dark one.
- **The folder `backups/below_your_limit`** holds documents that can be put back. The automatic
  clean-up of old backups must never count it as a backup.

---

## 4. Checking a change

```bash
pytest -q                                  # everything, about two minutes
python -m pyflakes jobhelper tests run.py status.py app_qt.py
```

After every batch of changes, without being asked:

1. The full test suite and pyflakes.
2. The guard test that no test starts an outside program (`tests/test_guards.py`, part of the suite).
3. Load the real window offscreen on the real data, **read-only**: open the lists and every job
   window, compare a checksum of the data folder before and after, look for QML warnings.
4. For anything that changes how a window looks: screenshots on made-up data, in both themes,
   and actually look at them. A colour that is right in the file can still not reach the label.

What tests may never do (the shared fixtures in `tests/conftest.py` enforce it): touch real
data, the Keychain or `.env`; ask Claude; send a notification; open a file, a folder or a web
page; read a real job board; put anything in the real Trash.

Before real data is changed by a script: close the app, make a backup with `vault.make_backup`,
then change it, and say what was changed.

---

## 5. Decisions already made

| Decision | Why |
|---|---|
| Scoring stays on the larger model | The smaller one gave the same band for only 14 of 29 real jobs. |
| Jooble postings keep their short summary | The site answers a program with a "prove you are a person" page. That is taken as a no; the window offers pasting the text. |
| Company-branded job pages are read from the page's own source | The page itself holds only a summary. The page's public key is used for that one question and never stored. |
| Any other page: only its published copy of the posting is read | Guessing which part of an unknown page is the posting would sooner or later score a job on a cookie notice. |
| A title-only score is capped at 40 and gets no documents | A letter written from a title can only be generic. |
| A required language the CV does not show caps the score at 25 | The model alone let such jobs through. |
| "Another profession" follows the roles you look for | The first list was written for software jobs. Measured on 543 real postings, the new rule decides the same and skips nothing that scored 30 or more. |
| The app does not invent job duties for interview stories | Stories come from the CV and the user's notes; "typical tasks" are labelled as general knowledge. |
| Removing old moved documents uses the Trash | Deleting cannot be taken back. |
| No Windows or Linux version | Not wanted. |

---

## 6. What is left to do

Checked against the whole code on 9 October 2026. Order matters for the last two.

**Found in the code check**

1. **Closed postings stay in New Jobs.** `agent2_search.prune_closed_leads` exists and is
   tested, but nothing calls it: a posting that no longer accepts applications is only caught
   when it is first found, never later.
2. **Text that is cut off.** 21 places still end a long text with "…" (rows of the lists, cards
   on the main screen, the job window's header) instead of wrapping.
3. **Errors that are swallowed.** 14 places catch any error and do nothing. Each needs a look:
   keep with a reason, or at least write it to the log.
4. **Helpers nothing uses.** `limitInfo` (bridge), `db.set_response_job`,
   `filters.is_too_senior_for`, `form_answers.parse_questions`, `vault.use_keychain` are only
   reached by tests. Use or remove.
5. **Resume button contrast.** White on blue is about 3.7:1, under the 4.5 the rest meets.
6. **Three large files.** `ui_api.py` (about 1,400 lines), `Main.qml` (about 1,100) and
   `qt_bridge.py` (about 950). Splitting `ui_api.py` by area would make the next big feature
   easier to add.

**Documentation**

7. **README refresh.** It predates most recent features and still explains English-only
   filtering with "because you don't speak Czech".
8. **Help window.** It does not yet describe moving documents and putting them back, picking
   the profession, or the Trash.

**For anyone's CV**

9. **Keywords for other professions.** `keywords.VOCABULARY` is about a hundred software
   technologies. "Keywords in the posting" and the "none of the technologies are in your CV"
   skip find little for a non-software CV.
10. **More professions.** Eleven fields, in English with some Czech words. Design, science,
    construction and the public sector are missing.

**Needs the user**

11. **Second mailbox** has only been tested with stand-ins, never with a real second account.
12. **Score all again** has never been run on the whole list with the current rules (about 26
    Claude calls).

**Then**

13. **The big feature** (to be described).

**Last**

14. **An app that opens without the terminal.** Expected parts: a real `JobHelper.app` with the
    existing icon; data moved out of the project folder to a per-user place, with a one-time
    move of existing data and backups; finding the Claude sign-in from an app started by
    Finder; the weekly run and the notifier pointed at the packaged app; first launch of an
    unsigned app on macOS. It is last because every item above changes files the package
    would freeze.
