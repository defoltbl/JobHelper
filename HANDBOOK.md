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
  reused for the same question elsewhere); its back end is `api_assistant`. `assistant_notes` keeps what the person asked it to remember and the last turns of the talk. `assistant_brain` is what Claude makes of a free request (an answer, or one
  action from a fixed list, checked before anything happens) and `api_talk` carries it out: your yes before
  any change, the briefing, the reminders, noticing a form, interview practice.
- **Keeping data safe:** `vault` (encryption, backups), `integrity` (signed rule files),
  `housekeeping` (old backups, logs, the Trash), `store` and `db` (jobs and replies).
- **Claude:** `llm` (every call goes through it; pauses at the limit), `usage`.
- **My details** (`details`): `check()` answers (clean values, problem); inside, `DetailsProblem` is raised by `RowList` and its kinds `JobList`, `DegreeList`, `LanguageList` (template method: `_cell`, `_before`, `_after`), `FileList` and `Salary`. `MyDetails` is the saved details as forms use them.
- **The window's back end:** `ui_api.Api` is a facade over ten services (OOP: one job per class,
  composition, no service imports another): `api_system`, `api_options`, `api_jobs`,
  `api_documents` (scores, moving documents, "not interested"), `api_replies`, `api_insights`,
  `api_interview` (dates, form answers, interview preparation), `api_letters` (letter editor, PDFs),
  `api_assistant` and `api_talk`; the shared helpers are in `api_core` (`Desktop`, `CvSource`,
  `JobEditor`). `qt_bridge` is the Qt side (signals, sign-in, Options, schedule) with its parts `bridge_runs` (search,
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
- **An event's day and start are read only by `planner.Event`**: "Coming up", the reminders, the calendar file
  and the thank-you note ask it. A dated line in a job's notes is `store.add_note`; a title the app gives a job it
  knows only by its company is one of `store.PLACEHOLDER_TITLES` (`store.has_real_title`).
- **Each small store is one object over one `vault.JsonFile`**: `assistant_notes.AssistantNotes`,
  `answer_memory.AnswerMemory`, `planner.CompanyNotes`. A file the data key cannot open raises `VaultError`;
  a save never treats it as empty, or it would write over it (`CompanyNotes` shows no notes, and the save gives
  `CompanyNotes.UNREADABLE`). The other JSON files use it too: `config.UI_SETTINGS` (Options), `api_options` `LAST_RUN`,
  the filtered-out list (`agent2_search`), `agent1_cv.PROFILE`, `details.FILE`. `load` raises for a damaged file (Options
  notes it, the CV analysis is made again), `read` gives None; each store keeps its own answer to a locked file (the
  last run, the filtered-out list and Options show nothing; the CV analysis and My details refuse). `usage.UsageLog` owns usage.json (not
  encrypted) and the counts of this run; `api_system` asks `usage.totals()` / `usage.by_tag()`.
- **A script for the page gets its values only through `form_fill.with_values`** (each `__NAME__` as JSON data, never
  code), and every answer of a page is read through `form_fill.page_reply` (refused with a message, or None). A new
  script and its reader use both; `tests/test_page_scripts.py` checks that no builder leaves a `__NAME__` unfilled.
- **One fill of a form is one `form_run.FormFillRun`** (read the page, find the job, plan, leave out what you named,
  draft answers, choose, tick, write and type again what the page threw away, attach, report). `api_assistant` only
  starts it and keeps `learned()` for "Learn my corrections". A new step is a method there, and a step that must
  stop raises `Stop(message)`.
- **Which pages the assistant works on is `form_fill.PageAddress`** (`is_web`: http or https with a host; `refused`: a
  Russian service; `refusal(doing)` says so in one sentence). Filling in, reading back, opening a framed form, judging a
  posting and noticing a form all ask it. The choices of a form are `form_run.FormChoices`, its file fields
  `form_run.FormFiles`; the plain checks of a form read back are `form_fill.plain_problems`.
- **The briefing's rules are `summary.briefing_lines` and `summary.nudges`** (worked out from the data, no Claude);
  `api_talk` only reads the data and asks them. The follow-up days come from `followup_days()`, as everywhere.
- **The window keeps no copy of a limit.** How long a typed text may be comes from the module that checks it,
  through `Api.limits()` (`win.limits` in QML) or with the data of a dialog (`columns` of My details, `max_part`
  of a preparation). A new limit goes into the owner and into that map; `tests/test_window_limits.py` keeps
  numbers out of the dialogs.
- **A form's limits and its "[to fill in]" rule are `form_answers`'s** (`MAX_QUESTION`, `MAX_ANSWER`, `unfilled`): the
  assistant and the answer memory ask it. A phone code is chosen only by `form_fill.code_option`, and a date of
  My details ("03/2023") is read only by `form_fill.RowDate`, whatever kind of field or menu the page has.
- **Every email scan ends with `agent5_responses.after_scan` and says so through its `ScanStats`** (`summary`,
  `closing_line`, `detail`, `notice`), in the window, `status.py sync` and the weekly run. What a fetch could not read
  (a folder, the second mailbox) travels in `email_client.Fetched.warnings` into `ScanStats.warnings`; no module
  keeps warnings between scans. How far back it reads is `config.scan_days()`; when a follow-up is due is
  `followup.saved_days()`.
- **On the command line, reading the mailbox stops one way** (`status.scan_inbox`, `status.fetch_mail`): Claude's limit
  saves what was read and ends with 3; a mailbox problem is one sentence (`mail_problem`) and 1. They raise
  `Stopped(code)`, and `main()` returns its code.
- **About you is its own window and `about_you.AboutYou` owns it**: the start-date preview (the form filler's
  `start_day`), the right-to-work choices, the salary estimate (`salary.estimate_available`) and `WorkNotes`, the
  notes per job. Everything that reads the notes calls `config.experience_notes()`, which asks `WorkNotes.text()`;
  `WorkNotes.size()` measures that same text, so nothing is ever cut. One line of "A different figure for" is checked
  only by `OptionsService.pay_problem`, on Add and on save; the CV's level is read only by `agent1_cv.seniority()`.
- **Find-as-you-type matches the start of a word** (`win.matchesStart` in Main.qml): the country picker and the
  suggestion fields use it. Do not filter a list with `indexOf` on its own.
- **Postings are scored only through `agent3_letters.Scorer`** (the batch prompt, the J-id answers, the one-by-one
  retry, the limit wait). A caller says only what it keeps (`record`). A job that got its documents ends with
  `mark_ready`, in a search and in `generate_for`.
- **A browser is a `chrome.Browser`**: its names, its switch, its messages and its AppleScript. A new browser is one
  more entry in `chrome.BROWSERS`; code that needs a browser's field asks the object, never a position in a tuple.
- **Two company names are one company only through `email_client.same_company`.** Never compare
  by "any shared word": "Accenture Czech Republic" and "PwC Czech Republic" share one. A legal form
  ("spol. s r.o.", "Corp", "LLC", "Limited") is never a word of the name: `email_client.LEGAL_WORDS`
  is the one list, for the company key and for the name words.
- **A reply moves an application only through `email_client.status_after`**: forward only, a rejection
  from any status. The scan, the progress check and filing a reply by hand all ask it.
- **Every call to Claude goes through `llm.ask`,** which refuses while `ANTHROPIC_API_KEY` is set.
  Do not add a second way to ask.
- **A CV's sections are found by their headings, whatever they are called** (`cv_tailor.sections`):
  never by a fixed list of names, or another person's CV loses a section.
- **Caches that outlive one search** are wrong in an app that stays open for days: each
  `job_sources.JobSource` forgets what it read in `reset()`, which `agent2_search.search` calls first.
  A new board is a new `JobSource` in `job_sources.all_sources()`; the search itself does not change.
- **A new search filter is one `Sift` in `agent2_search.SearchFilters.sifts()`**, in its place in the order. The
  duplicate check stays last (`apply`): it keeps one copy only after every filter that can drop a copy has run.
  The country of a search is `filters.Placement.home`: never work it out again from the city or Options.
  The window and `run.py` (the weekly run) make the search with `SearchSettings.from_options` and add its
  postings with `take_in`: a new setting or step goes there once, not into each of them.
- **The folder `backups/below_your_limit`** holds documents that can be put back. The automatic
  clean-up of old backups must never count it as a backup.

- **Heavy work in a background thread still holds the window up.** Python runs one thread at a time, so
  thousands of small steps in a worker (the Insights keywords were 59,000 searches) make every call from
  the window queue behind them. Give such work short rests (`keywords.read_ahead`), keep it away from
  animations (it starts after the welcome screen), and keep `sys.setswitchinterval` in `app_qt.py`.
- **Qt says a paragraph begins where its box begins, not where its words stand.** A line that did not fit at the end of a
  page is drawn on the next one while the block still "starts" on the old one. The PDF builder asks for the first
  line's place (`top_of`); a heading was left alone at the bottom of a page before it did.
- **A browser's scripting dictionary must be tried, not read.** Opera GX's file names the command that runs a script in a
  page, inside a comment: a search for the words found it, and the first live request failed. Ask the browser a harmless
  `1 + 1` before saying it works. A refusal the app does not know is now written to the trouble log with its text.
- **A list's own entries must not be part of its name.** A label that is only written beside a list is found by reading the
  words around it. With 250 countries the entries filled the 300 characters read, the label was lost and the list was left
  (first real form, 10 October 2026). `beside()` in `form_fill.READ` reads the words without any list's entries and stops at a
  block that holds other fields; test forms need lists as long as real ones (`tests/fixtures/forms/lists.html`).
- **The trouble log is data too.** `trouble.note` is sent to a spare folder by the test guard; two test lines reached the real
  log before that.
- **A text field does not let go of the focus by itself.** In Qt Quick a press on empty space leaves the field
  outlined with its cursor blinking. Every window with a field needs `FocusCatcher {}` in its background and as the
  first child of each scroll area (it also covers the space under short content); a test fails for a window without one.
  A list (`ListView`) beside a field needs `FocusCatcher { z: 2 }` over its rows: the rows take the press, so a
  catcher under them never sees it. It passes the press on, so rows and scrolling work as before.
- **An answer sent from a worker thread must carry plain values.** The start-up check travels inside the
  connection answer as text (`info.health`, JSON) and the window parses it.
- **Where the data is, is decided once, when `config` is imported.** `config.DATA_DIR` comes from
  `home.DataHome`; modules keep paths made from it. So the one-time move into the Library happens in
  `app_qt.main()` before anything reads data, and the app then starts itself again. Tests set
  `JOBHELPER_HOME` to a temporary folder in `conftest.py`, and the guard watches both the Library
  folder and the old `data/`.
- **Word files and PDFs hide text from `git grep`.** The first privacy check missed a real CV in
  `tests/fixtures/*.docx` because the text is zipped. `scripts/push_check.py` opens them, and the
  pre-push hook runs it on every push. The repository will be public.
- **In the sandbox, "home" is the widget's container.** `homeDirectoryForCurrentUser` / `NSHomeDirectory()`
  point to ~/Library/Containers/<widget id>/Data; the real home comes from `getpwuid(getuid())`. The
  temporary-exception path in the entitlements is relative to the real home. After installing a new
  build, `pkill -x JobHelperWidget` makes chronod start the new binary at its next refresh.
- **The app asks macOS to redraw the widget, from its own process.** Only the app that holds a widget may call
  `WidgetCenter`, and chronod checks the caller is the app's main program: a second program in Contents/MacOS was
  refused ("Resolved bundle path does not match executable", ChronoCoreErrorDomain Code=10). So the app loads
  `Contents/Frameworks/libJobHelperWidgetReload.dylib` (widget/WidgetReload.swift) with ctypes and calls
  `jobhelper_reload_widgets()`. Reloads come from a daily budget, so
  `widget_feed.WidgetReloader` asks only when what the widget shows changed (usage alone: every 30 minutes at most).
  Buttons inside a widget need App Intents metadata from Xcode; with the Command Line Tools only, there is no refresh button.
- **A passed date leaves "Coming up" one hour after its time** (`planner.PASSED_AFTER`, `planner.leaves_at`). The
  summary for the widget carries that moment with each date ("leaves"), so the widget has no copy of the rule: it
  hides the date then (`When.gone`) and puts a timeline entry there, also when the app is closed.
- **Notifications come from the app's own process** (`macos/Notify.swift`, `notify.AppNotifier`). A script app
  (osascript applet) cannot ask macOS for permission, so macOS kept every notification without showing it, also
  not in the Notification Center. macOS asks an app once; a question that goes away unanswered (the program
  ended) counts as "Don't Allow", which only the person can change in System Settings. So `--notify-test`
  waits for the answer, and Options says in red when notifications are off.
- **A widget extension must start in `_NSExtensionMain`.** Linked like a plain program (entry `main`),
  `WidgetBundle.main()` returned at once on macOS 26: chronod logged "query failed … Code=4099" and the
  gallery stayed empty. Link with `-Xlinker -e -Xlinker _NSExtensionMain`. Read logs with `/usr/bin/log`:
  in zsh, `log` is a builtin and prints nothing useful.
- **The widget is built without Xcode.** `swiftc -application-extension` + an `.appex` with
  `NSExtensionPointIdentifier = com.apple.widgetkit-extension`, ad-hoc signed with sandbox
  entitlements (a temporary exception for one home-relative folder), then the app signed again.
  `pluginkit -m -i local.jobhelper.app.widget` shows whether macOS knows it. Dropped Qt parts left
  SYMLINK entries behind that broke `codesign --strict`; the spec drops those links too.
- **An app started by Finder or launchd works in `/`.** The Claude program watches its working folder
  ("Watching / for /.claude to appear" in its debug log), and that made macOS ask the first user of
  JobHelper.app for Desktop, Downloads, Music, removable disks and other apps' data. Everything now
  works in `config.work_dir()`; tests in `test_packaging.py` keep it so.
- **A packaged app carries only what it can see being imported.** A module loaded by name
  (`importlib`, the weekly run's `run`/`status`, `PySide6.QtQuick` for the picture) must be in the
  spec's `hiddenimports`; the window check of the built app fails when one is missing.
- **Opening the real window uses up reminders.** `Bridge.remind` marks the reminders of the day as given.
  A read-only check of the real window must replace `ui_api.Api.due_reminders` with an empty list; a
  check on a day with an interview once used up that day's morning reminder.
- **Under test the window's loop keeps Python to itself for one whole wait**, so a worker only moves
  between two waits. `Ui.wait` waits in short steps for that reason; do not call `QTest.qWait` directly.
- **Rows made by a `Repeater` are not found by `findChild`.** Use `ui.seen(part)` / `ui.drawn(name)`.
- **The usage numbers are a snapshot from Claude's last answer.** `usage.windows()` corrects them: a
  refusal fills the window it names until its reset, a window past its reset time is empty. Everything
  that shows or tests the limit goes through it.
- **The window is taken down before the bridge** when the app closes (`app_qt.shut_down`), or every binding
  that calls the bridge prints an error on the way out.
- **One claim check for every text in the person's voice** (`claims.ClaimCheck`): the letter, the form answers and
  the interview preparation ask it; only the interview allows the honest bridge ("I have not used X"). In the
  preparation, `Preparation.voice()` is the one list that is both sent back to the model and marked for the user:
  a part added to the sheet goes into that list, or it is checked in one place only.
- **A sentence of a letter is a claim only where the candidate is the one doing it** (`cover_letter.borrowed_claims`):
  "the role caught my attention because it covers X" describes the role. Measure a change to these checks on the
  letters and CVs already written before it ships.

---

## 4. Checking a change

```bash
pytest -q                                  # everything on every core (pytest-xdist), about one minute
python -m pyflakes jobhelper tests run.py status.py app_qt.py
```

The window tests are four files (`tests/test_window_main.py`, `_jobs`, `_scores`, `_assistant`). The tests of one
file share one window and follow on from each other, so each file is a worker group of its own
(`pytestmark = pytest.mark.xdist_group("<file name>")`, `--dist loadgroup` in pytest.ini) and the four run side by side:
about one minute instead of three. Each file gets a fresh window and fresh data (`ui` in conftest.py, built by
`tests/window_harness.py`). A test that needs data an earlier file made sets it up itself. A new window test file needs
a group too (`tests/test_test_setup.py` checks it). To run one test alone without the workers: `pytest -n 0 <test>`.

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
| A remote job tied to one country is kept only for your country and the countries you add, also with "Anywhere in the world" | Such a job asks you to live in that country or to have the right to work there. "Anywhere" adds only jobs for whole parts of the world ("Remote – APAC"). One rule, `places.RemoteReach`, for the search, Options and the window. |
| The app knows every country, each with its part of the world | An unknown name was read as "no place": "Remote, South Korea" passed as open to anyone. Codes that are also US state codes (IL, ID, MA …) count as the country for someone who searches there; "City, DE" stays Germany. |
| Duplicates are removed after all other filters | The copy kept as the duplicate's winner could then be dropped (in Czech, too old), and the other copy was lost with the reason "duplicate". |
| The rule files and the letter template are optional | Without them the built-in rules and a plain letter are used, so their absence is not reported as a problem. |
| A search role the app does not know is asked about once, not refused | The words it knows grew up with software jobs. |
| No Windows or Linux version | Not wanted. |
| No Russian services | The owner's rule. A mailbox or server of one is refused with a plain message. |
| A term of the posting left in a CV or letter is shown, not cut out | Cutting whole sentences removed fair wording ("version control" for someone who uses Git). Measured on 53 real CVs and letters before it shipped. |
| The user guide has no terminal commands | It is for someone who only uses the app. What needed a command (the recovery key, backups) got a button. |
| A mailbox is tried before it is saved | Only the form of the password was checked, so a wrong one showed up at the first scan. |
| Outlook.com, Proton and Tuta are refused with an explanation | They cannot be read with a password; failing later would be worse than saying so at once. |
| The salary estimate is used only for software roles in Czechia | It is a table of Prague junior software pay. Anywhere else no figure is better than a wrong one. |
| The assistant fills in forms in the person's own browser, through Apple events (Chrome first; Brave, Edge, Opera and Safari since; Opera GX and Firefox cannot be reached this way and are said to be impossible) | The owner's choice ("I tap on him and ask to fill the form in Chrome"). The form is filled where the person is signed in; nothing is installed. A browser inside the app was removed earlier, and an extension would have to be installed by hand. |
| The assistant presses only a menu, an entry of a menu, a radio button and a button that adds a row | The owner allowed menus on 10 October 2026 and rows on a button ("do all points") the same day. It still never presses a button that sends or continues, never ticks a box and never sends: the script that presses reads what it is given, and the words of an add button, again before it acts. |
| A free request is decided by Claude and checked by the app | The owner chose this knowing it costs a call per request. Claude names one action from a fixed list; anything else is dropped. An action that changes data is asked about in the app's own words and done only after a yes. |
| The one tick box the assistant may tick says that a job goes on | The owner allowed it on 10 October 2026 ("do all points"). A box that agrees to anything is refused by its words. |
| Answers are not streamed word by word from Claude | A decision is one object that must be checked whole before anything of it is shown or done. The window says what is being done meanwhile and writes the checked answer out. |
| A note the person asks the assistant to remember changes only its answers | Changing what a search finds through a sentence in a talk would be app logic nobody can see. The Options do that. |
| Noticing a form in the browser is off until turned on | It means looking at the browser without being asked. When on, only the address, the title and the number of empty fields of the tab in front are looked at. |
| A review reads the values of a form | A deliberate choice. Passwords and files are never read, and personal and payment values are not sent to Claude. |
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
   one, a framed one, each filled in a browser engine by the real code), **not yet on real sites in the person's browser.**
   Sites that build their fields in unusual ways (their own drop-downs, forms inside a frame from another site,
   pages that rebuild a field after it is written) will need a look one by one. Tick boxes and dates are left to
   the person on purpose. File fields for the CV, the letter and other attachments are given the job's documents
   (added after the first real form, 10 October 2026); a page that draws its uploader without a file field
   until it is clicked cannot be reached, and the files are then shown in Finder as before.

**Needs the person**

- **A live trial of the assistant.** Turn on the browser's switch (Allow JavaScript from Apple Events; the My details
  page says where it is), save My details, and try it on a few real application forms and on real questions.
  Every form test so far ran in the test area; the prompts were tried against the real Claude on invented data
  (19 calls, 10 October 2026). The first live try was in Opera GX and failed: its dictionary lists the command
  that runs a script, but commented out. Chrome, Brave, Edge, Opera and Safari have not been tried live on this Mac.
- Decided on 10 October 2026: in the PDFs the next section of the same chapter may begin in a gap (one section further at most, never a chapter; figures and tables keep their order). The whole-window size is `QT_SCALE_FACTOR`, set in `app_qt.apply_text_size` from the option `text_size`, so it needs a restart. When the person can start stays in Options (`about_start`); `form_fill.start_day` turns it into a day for date pickers.
- Rows in forms (10 October 2026, from real forms): a job's block also holds its own Location and Role description (`job_location`, `job_description`, by nearness to the row's fields, `ROW_NEAR`); dates may be split into Month and Year boxes (`part`, `group` from READ); languages are a third list (`lang_name`, `lang_level`, `fluent_box`). The two tick boxes the assistant may tick are "I currently work here" and "I am fluent in this language"; nothing else.
- The README's Author section is the one tracked place that names the person (since 10 October 2026). Code, tests and the other documents still name nobody.
- The 19 jobs whose documents were moved to the backup on 9 October: they can be put back until about 16 October.
- Whether the README should name its author (the rule keeps the name out of tracked files).
- Whether the text of the next section may come forward in the PDFs to fill the space a figure left at the end
  of its own section (today it may not, so some pages keep a gap).

**Then, for the assistant**

- Whatever the live trial shows. Menus are the likeliest: every component library draws them a little
  differently, and the script knows the common pattern (a box that opens a list of `role=option` entries).
- A date that is not part of a job or a degree (the day you can start, from About you).
- A text size for the whole window: the assembly line grows with the window, the side columns do not.

**Last**

- **An app that opens without the terminal.** DONE 2026-10-16: `python scripts/build_app.py` (PyInstaller, `packaging/JobHelper.spec`, checked by `AppCheck`). Expected parts: a real `JobHelper.app` with the
  existing icon; data moved out of the project folder to a per-user place, with a one-time
  move of existing data and backups (DONE: `home.DataHome`, ~/Library/Application Support/JobHelper); finding the Claude sign-in from an app started by
  Finder (DONE: `claude_cli.ClaudeCli` uses the SDK's own copy); the weekly run and the notifier pointed at the packaged app (DONE: `--weekly`, `schedule.refresh`, notifier falls back to osascript); first launch of an
  unsigned app on macOS; the technical documentation updated for installing without Python.
  It is last because every item above changes files the package would freeze.
