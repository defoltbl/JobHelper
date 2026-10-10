# JobHelper handbook

What to remember about this project: how to use the app, the rules it is built by, how the
code is laid out, how a change is checked, what was decided and why, and what is left to do.

- How to use each part of the app, step by step and with pictures, is in [docs/GUIDE.md](docs/GUIDE.md).
- Installing, the command line, the structure of the code and the tech stack with its reasons are in
  [docs/CODE.md](docs/CODE.md). Every command with its options is in [COMMANDS.md](COMMANDS.md).
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
| File a reply under the right application | Responses → the reply → **File under…** |
| Have a CV and letter written for one job | Job window → **Write CV and letter** |
| Go through many jobs quickly | New Jobs → narrow the list → **Review these … one by one** |
| See what the app has used, and what went wrong quietly | Help → **Usage and problems** |
| Back up everything, or take a readable copy out | Options → Notifications and storage → **Back up everything** |
| Save the key you need on a new Mac | Account card → *Data protection* → **Recovery key** (do this once) |

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
- Secrets (the mailbox passwords, the data key) live in the macOS Keychain and are never
  printed, logged or put in an error message. An address in an error loses its query part.
- **No Russian service is added or used**, anywhere: mail providers, job boards, APIs, hosts.
  `mailhosts.never_used` refuses such a mailbox or server, and a test keeps the provider list clean.

**What is written for the user**
- A CV, a letter, a form answer or an interview story never claims anything that is not in the
  master CV or in the user's own *More about your work* notes.
- A letter the user wrote themselves is never rewritten, replaced or moved. Only documents the
  app wrote can be.
- What the app cannot settle by itself is shown, not hidden: a term of the posting that an adapted CV
  or a letter still states as experience after one retry is named in the job window (`cv_check`,
  `letter_check`); a sentence is not cut out silently.
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
| `agent2_search` | searches the boards, filters, notes why a posting was dropped, second read of empty postings, notices closed ones |
| `agent3_letters` | scores (five postings per call), caps, writes the CV and letter |
| `agent4_tracker` | builds the Excel files |
| `agent5_responses` | reads replies, files them to applications, analytics |

### Around them

- **Reading postings:** `scrapers_cz` (jobs.cz, prace.cz, company-branded pages), `scrapers_intl`
  (LinkedIn guest pages), `scrapers_remote`, `scrapers_ats` (company career systems),
  `scrapers_page` (any other page: only the copy it publishes for search engines).
- **Rules without a model call:** `filters` (level, years, languages), `prefilter` (another
  profession, unwanted roles), `keywords`, `salary`, `merge`, `followup`, `planner`, `language`
  (which language an ad is written in), `mailhosts` (which server a mailbox is read from), `places` (which city is in which country, and what
  counts as "here" for a search).
- **Writing:** `cv_tailor`, `cover_letter`, `letters` (your own letters), `form_answers`,
  `interview_prep`, `prep_doc`, `pdf`.
- **The assistant:** `assistant` (what a typed request means), `details` (the person's own details: contacts, jobs, degrees, salary with currency, files; encrypted), `chrome` (the tab in front in Google Chrome, through Apple events), `form_fill` (the page
  scripts, what each field is, which job a page belongs to), `form_choices` (lists, radio buttons, menus,
  numbers: settled by the details, else by one call to Claude), `answer_memory` (the person's own wording,
  reused for the same question elsewhere); its back end is `api_assistant`.
- **Keeping data safe:** `vault` (encryption, backups), `integrity` (signed rule files),
  `housekeeping` (old backups, logs, the Trash), `store` and `db` (jobs and replies).
- **Claude:** `llm` (every call goes through it; pauses at the limit), `usage`.
- **The window's back end:** `ui_api` (what the window can ask for: lists, one job in full, hand
  edits, Options) with its parts `api_documents` (scores, moving documents, "not interested"),
  `api_interview` (dates, form answers, interview preparation) and `api_letters` (letter editor,
  PDFs); `qt_bridge` is the Qt side (signals, sign-in, Options, schedule) with its parts `bridge_runs` (search,
  scan, scoring again, stopping, pausing on the limit) and `bridge_jobs` (what the job windows ask for).
- **The main window:** `Main.qml` holds the state, the palette and the dialogs; the screen itself is
  `NavPanel` (left), `StagePanel` (robots and status line), `AssistantBot` (the assistant at the end of the line) with its window `AssistantDialog`, `StatusPanel` (right), `PipelineBar`
  (bottom), and `views.js` fills the lists.
- **When something fails quietly:** `trouble.note()` writes one line to `data/app_trouble.log`.
  An error is never swallowed without either a reason in a comment or a line there.

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
- **A part of the main window cannot see names inside another part.** What everyone needs (the
  status line `ticker`, the robots `a1`…`a5`) is handed up as a property of the window in
  `Main.qml`. In a part, `Robot { theme: theme }` binds the robot's theme to itself.
- **`Api` and `Bridge` are each one class made of several files.** A method name defined in two of them would silently
  hide one (there is a test).
- **Lists that decide what is skipped** (`prefilter.FIELDS`, `keywords.VOCABULARY`) must be
  measured on the real postings before a change ships: nothing that scored 30 or more may be
  skipped. A word that an ordinary posting uses ("research", "architect", "compliance") does
  not belong in them.
- **Two company names are one company only through `email_client.same_company`.** Never compare
  by "any shared word": "Accenture Czech Republic" and "PwC Czech Republic" share one.
- **Every call to Claude goes through `llm.ask`,** which refuses while `ANTHROPIC_API_KEY` is set.
  Do not add a second way to ask.
- **A CV's sections are found by their headings, whatever they are called** (`cv_tailor._sections`):
  never by a fixed list of names, or another person's CV loses a section.
- **Caches that outlive one search** are wrong in an app that stays open for days: clear them at
  the start of `agent2_search.search`.
- **The folder `backups/below_your_limit`** holds documents that can be put back. The automatic
  clean-up of old backups must never count it as a backup.

- **Heavy work in a background thread still holds the window up.** Python runs one thread at a time, so
  thousands of small steps in a worker (the Insights keywords were 59,000 searches) make every call from
  the window queue behind them. Give such work short rests (`keywords.read_ahead`), keep it away from
  animations (it starts after the welcome screen), and keep `sys.setswitchinterval` in `app_qt.py`.
- **A text field does not let go of the focus by itself.** In Qt Quick a press on empty space leaves the field
  outlined with its cursor blinking. Every window with a field needs `FocusCatcher {}` in its background and as the
  first child of each scroll area (it also covers the space under short content); a test fails for a window without one.
- **An answer sent from a worker thread must carry plain values.** The start-up check travels inside the
  connection answer as text (`info.health`, JSON) and the window parses it.
- **Under test the window's loop keeps Python to itself for one whole wait**, so a worker only moves
  between two waits. `Ui.wait` waits in short steps for that reason; do not call `QTest.qWait` directly.
- **Rows made by a `Repeater` are not found by `findChild`.** Use `ui.seen(part)` / `ui.drawn(name)`.
- **The usage numbers are a snapshot from Claude's last answer.** `usage.windows()` corrects them: a
  refusal fills the window it names until its reset, a window past its reset time is empty. Everything
  that shows or tests the limit goes through it.
- **The window is taken down before the bridge** when the app closes (`app_qt.shut_down`), or every binding
  that calls the bridge prints an error on the way out.
- **A sentence of a letter is a claim only where the candidate is the one doing it** (`cover_letter.borrowed_claims`):
  "the role caught my attention because it covers X" describes the role. Measure a change to these checks on the
  letters and CVs already written before it ships.

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
4. For a change that can be seen: take a picture of the window and look at it. A test that reads a
   text does not notice that the text is not drawn.
5. Documentation, when a change can be seen:
   - `docs/GUIDE.md` is the **user guide**: for someone who only uses the app. It contains no terminal
     commands and no code. If the guide needs something, the window must be able to do it.
   - `docs/CODE.md` is the **technical documentation**: installing, the command line, the structure of the
     code, tests, and how the documentation itself is made. `COMMANDS.md` stays the full command reference.
   - Both follow one pattern (the rules are in `docs/CODE.md`, "Write in the house style"): headings that start with a verb,
     *Overview*, *Prerequisites*, numbered steps, tables for reference, *Note / Tip / Important / Warning*
     boxes, buttons in bold exactly as the app writes them.
   - Every figure and every table has a numbered caption and is referred to from the text. Numbers follow
     the chapter, as in a thesis ("Figure 4.2 – Title" under a picture, "Table 4.2 – Title" above a table).
     After adding one, run `python scripts/guide_number.py`.
   - The PDFs are laid out like a thesis: contents with dotted lines to the page numbers, the page number at
     the top right, no lists of figures and tables, a long table continued under "Continuation of Table N".
   - Take the guide's pictures again when a pictured window changed
     (`pytest tests/guide_shots.py -q -o addopts=""`) and look at them.
   - Make the PDFs again: `python scripts/guide_pdf.py`. They are laid out like a thesis (title page,
     contents, lists of figures and tables, page numbers) and keep the page rules: a figure is never split,
     a table stays on one page, a longer one continues between rows with its heading row repeated, a
     heading is never left alone at the bottom of a page. `tests/test_docs.py` checks all of this.

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
| The keyword and profession lists leave out ordinary words | With 235 keywords and 17 professions, 4 of 543 real postings are decided differently, none of them one that had scored 30 or more. |
| A closed posting with documents is marked, not removed | Removing it would throw away a letter and CV without asking. One without documents goes to the filtered-out list. |
| Only LinkedIn pages are asked whether a posting closed, 40 per search, each at most every 3 days | It is the only board that answers clearly, and asking every page on every search would hammer it. |
| The app does not invent job duties for interview stories | Stories come from the CV and the user's notes; "typical tasks" are labelled as general knowledge. |
| Removing old moved documents uses the Trash | Deleting cannot be taken back. |
| The rule files and the letter template are optional | Without them the built-in rules and a plain letter are used, so their absence is not reported as a problem. |
| A search role the app does not know is asked about once, not refused | The words it knows grew up with software jobs. |
| No Windows or Linux version | Not wanted. |
| No Russian services | The owner's rule. A mailbox or server of one is refused with a plain message. |
| A term of the posting left in a CV or letter is shown, not cut out | Cutting whole sentences removed fair wording ("version control" for someone who uses Git). Measured on 53 real CVs and letters before it shipped. |
| The user guide has no terminal commands | It is for someone who only uses the app. What needed a command (the recovery key, backups) got a button. |
| A mailbox is tried before it is saved | Only the form of the password was checked, so a wrong one showed up at the first scan. |
| Outlook.com, Proton and Tuta are refused with an explanation | They cannot be read with a password; failing later would be worse than saying so at once. |
| The salary estimate is used only for software roles in Czechia | It is a table of Prague junior software pay. Anywhere else no figure is better than a wrong one. |
| The assistant fills in forms in the person's own Chrome, through Apple events | The owner's choice ("I tap on him and ask to fill the form in Chrome"). The form is filled where the person is signed in; nothing is installed. A browser inside the app was removed earlier, and an extension would have to be installed by hand. |
| The assistant presses only a menu, an entry of a menu and a radio button | The owner allowed choosing from menus on 10 October 2026 ("do it"). It still never presses a button, never ticks a box and never sends: the script that presses checks what it is given. |
| Only what the person wrote or corrected is remembered as their wording | A draft nobody read is not their answer. An answer that names its company is not offered to another one. |
| A free question to the assistant is one Claude call with facts from the app | So an answer cannot come from anywhere else; when the facts do not hold it, the assistant says so. |
| A request to the assistant is understood by its words, not by a model | It costs nothing and always means the same. Only a form's open questions go to Claude, in one call. |
| A table or a picture is never split across pages in the PDFs | The owner's rule for the documentation; a long table continues between rows with its heading repeated. |

---

## 6. What is left to do

Everything found by reading the code and by the runs on real data up to 10 October 2026 is done (see CHANGELOG).

**Checked on real data, 9 and 10 October 2026** (app closed, a backup before each step)

- Score all again; documents from a higher score moved to the backup; one scan over 90 days of both mailboxes.
- 17 replies filed under the right application with **File under…**; the statuses that followed were corrected.
- A search that wrote the documents for the jobs that had risen above the limit.
- A whole run for an invented accountant on real postings, in a throwaway folder: profile, search, scoring,
  adapted CV and letter. It showed that the adapted CV could state the posting's words as experience; the
  check for that (`cv_tailor.borrowed_claims`) came out of it.

**Known limits** (said in the guide where they matter)

1. **The built-in salary estimate covers software roles in Czechia only.** Elsewhere the person enters a figure.
2. **Outlook.com, Proton and Tuta mailboxes cannot be read** with a password. A sign-in window for Outlook
   (OAuth) would be a piece of work of its own: registering the app with Microsoft, a browser step, tokens in
   the Keychain.
3. **National job boards exist for Czechia only** (jobs.cz, prace.cz). Other countries rely on LinkedIn, company
   career sites and the remote boards. Adding one board per country is open-ended; add one when a person needs it.
4. **The check that nothing is claimed beyond the CV** is strongest for technology names (a fixed list) and for
   two-word terms of the posting (`borrowed_claims`). A single borrowed word, or a claim in the cover letter that
   is worded freely, can still pass: the person reads both documents before sending, and the guide says so.
5. **The layout markup of the windows** (about 5,500 lines of QML) was scanned by a script for texts that can
   be cut and the finds were fixed; it was not read line by line. The window tests and the guide's pictures cover it.

6. **The assistant was tested in its test area** (`tests/fixtures/forms/`: a plain form, a component-built one, a long
   one, a framed one, each filled in a browser engine by the real code), **not yet on real sites in the person's Chrome.**
   Sites that build their fields in unusual ways (their own drop-downs, forms inside a frame from another site,
   pages that rebuild a field after it is written) will need a look one by one. Tick boxes, dates and file
   uploads are left to the person on purpose.

**Needs the person**

- Turning on Chrome's switch (View > Developer > Allow JavaScript from Apple Events) and trying the assistant
  on a few real application forms; what it leaves or gets wrong there decides the next step.

**Then, for the assistant**

- Rows a form adds on a button (**Add another job**): the assistant never presses buttons, so it fills the rows
  that are shown. Pressing such a button would be a new permission for the owner to give.
- The dates of a job or a degree in a form (month and year lists differ on every site).

- Whatever the trial on real sites shows. Menus are the likeliest: every component library draws them a little
  differently, and the script knows the common pattern (a box that opens a list of `role=option` entries).
- Date fields (a start date from About you).

**Last**

- **An app that opens without the terminal.** Expected parts: a real `JobHelper.app` with the
  existing icon; data moved out of the project folder to a per-user place, with a one-time
  move of existing data and backups; finding the Claude sign-in from an app started by
  Finder; the weekly run and the notifier pointed at the packaged app; first launch of an
  unsigned app on macOS; the technical documentation updated for installing without Python.
  It is last because every item above changes files the package would freeze.
