# JobHelper — Command Cheat Sheet

Quick reference for every command. Run all of these from the project root with
the virtual environment activated.

```bash
cd /path/to/JobHelper
source .venv/bin/activate
```

---

## 0. One-time setup

```bash
python3 -m venv .venv                 # create the virtual environment
source .venv/bin/activate             # activate it (do this every new terminal)
pip install --require-hashes -r requirements.lock   # install the exact, hash-checked packages
                                      # (or: pip install -r requirements.txt)

cp .env.example .env                  # optional settings (never put the Gmail password here)
claude auth login                     # sign in with your Claude subscription
claude auth status                    # verify: "loggedIn": true
```

Put your CV (English) in `data/cv/` — e.g. `data/cv/FirstnameLastname_CV_EN.docx`.

**Important:** do NOT set `ANTHROPIC_API_KEY` — leaving it unset is what makes the
app use your subscription instead of the paid API.

**No terminal?** After `pip install` + `python app_qt.py`, the app's welcome
card (and later the **Account** chip) handles the rest: Claude login, your Gmail
email + App Password, and picking your CV — so you can skip the `.env` and
`data/cv/` steps.

**Do this once after the first start** — save your recovery key (see section 10):

```bash
python status.py security recovery-key
```

---

## 1. Desktop app (window + robots)

The whole pipeline, as a window: the 5 agents are robots on a factory
conveyor belt, jobs ride the belt, and you drive everything with buttons.

```bash
python app_qt.py                      # open the JobHelper window (native Qt app)
```

Inside the window:
- **Run search** — runs Agents 1→4 (the robots work with their hands as each runs).
  While it runs the button becomes **■ Stop**: the run ends after the step it is on
  (one search request, one job, one email) and everything finished before that is saved.
- **When Claude's limit is used up** — at 99% of the 5-hour or 7-day window (or when Claude
  says the limit is hit) the run **pauses** instead of failing job after job: everything
  done so far is saved, a warning window opens with a sound, and **Stop** is replaced by a
  grey **Resume** button whose tooltip says when the limit resets. When it has reset the
  button turns blue; press it and the run continues with the job it was on. A small
  **Stop** button next to it ends the run instead. From the command line `run.py` saves and
  exits with a message; run it again later and only the unfinished jobs are done.
- **Scan email** — runs Agent 5 (Postman reads inbox replies), with a real progress bar.
- **New Jobs / Applications / Responses / Analytics** — click to see tables;
  each row has *open* buttons for the cover letter, tailored CV, or Excel file.
- **New Jobs rows** — *open ↗* opens the job posting in your browser (to apply),
  then *mark applied* moves the lead to Applications.
- **Click any job row** — opens the job in full: the description, why it got its
  score, which keywords from the posting are in your CV and which are not, notes,
  and buttons for the posting, CV, letter and their PDF copies.
- **Full-time only** — Options switch (on by default) that hides part-time roles.
  Jobs asking for up to 2 years of experience are kept: your internships count as experience.
- **Email scan period** — Options → *Scan emails from the last N days* sets how far back
  **Scan email** looks. Emails that were already read are skipped, so a long period
  costs nothing extra after the first scan.
- **Change an application by hand** — in the job window: **Waiting / Interview / Offer /
  Rejected** buttons (for news that did not come through the scanned mailbox) and an
  **Applied on** date field (YYYY-MM-DD). A date you set is never changed by emails.
- **Same application twice** — when one application was recorded twice (for example
  "CSOB" from your letters folder and "ČSOB (KBC)" from an email), certain cases are merged
  automatically after each scan; uncertain ones show a card with **Merge into one** /
  **They are different**. Nothing is lost in a merge, and your own letter stays protected.
- **Fewer Claude calls per search** — postings that are plainly another profession, need
  another language or a far higher level are skipped before scoring (shown as *skipped*
  with the reason; **Score it anyway** sends one to the next run), and the rest are scored
  five postings per call.
- **Second mailbox (optional)** — Account card → *Job email* → **Add** under "Second
  mailbox". Its replies are read in the same scan; one mailbox is enough if you only use one.
- **Skip words** — Options → Search → *Skip titles with*: jobs whose title contains one of
  these words are left out of the search (default: intern, internship). *…but keep titles
  with* lists exceptions that beat a skip word. Whole words only: "intern" does not match
  "Internal". A search role may not contain a word you skip.
- **Responses** — click a reply to read it in full (what it says, the rejection reason, the
  next step, subject and sender) and jump to its application.
- **Analytics** — applications by status and reply emails by kind, each group adding up to
  its total.
- **Search, filter, sort** — New Jobs, Applications and Responses have a search box (company,
  role, place; all words must match), filter chips with counts (strong / moderate / stretch /
  no documents; or by status; or by kind of reply) and a sort menu. The title shows "12 of 116".
- **Not interested** — in a lead's window. The job leaves the list, its app-written CV and
  letter go to an encrypted backup, and later searches do not bring it back (also not as a
  repost). The *not interested* filter chip in New Jobs lists them with **restore**.
- **Edit letter** — in the job window, for letters the app wrote (never your own). Edit the five
  paragraphs, or **Rewrite this paragraph** with an optional note about what to change (asks
  Claude once or twice). Save rewrites the Word file and PDF with the same head, date and
  layout; the previous version is kept in an encrypted backup. Rule breaks in a hand edit
  are shown as notes, not refused.
- **Insights** (left column) — worked out on your Mac, no Claude call: which kinds of role and
  which sources got you interviews and which only rejections; how each search keyword performs
  (a keyword whose jobs never reach your letter score is marked *drop?*); and **Skills to
  learn**: technologies the postings ask for most that are not in your CV. That list is only
  shown; nothing from it is ever added to a CV or letter.
- **Interview preparation** — in an application's window: **Prepare** asks Claude (once or
  twice) for about twelve likely questions with answers built only from your CV, questions to
  ask them, and topics to revise. It is saved with the job; **Copy all** puts it on the
  clipboard. An answer that claims something your CV lacks is marked "Check this answer".
- **Help** — the button under Options explains the app in ten short topics (what it does, a
  normal week, scores and labels, the limit, privacy, what to do when something looks wrong).
- **Last run card, cost rows** — *You paid: $0 · subscription* and *Same work via API: ≈ $…*,
  the estimated price of the same work with pay-per-use API billing (running total).
- **About you** (Options) — *Right to work* and *You can start*: the only personal facts,
  besides your CV, that letters and interview answers may state. Left empty, they are not mentioned.
- **Notifications** (Options, on by default) — a macOS notification when a search or scan
  finishes or pauses on the limit while the app is in the background, and always for an
  interview invitation. The weekly run notifies too.
- **Keep backups** (Options) — only the newest N backups in `data/backups/` are kept; older ones
  are deleted for good at every start (0 = keep all). Weekly log files keep their last 400 lines.
- **A date to remember** (job window of an application) — an interview, deadline, test task or call with a
  date (`YYYY-MM-DD`), an optional time and a note. The next ones are listed under
  **Coming up** on the main screen; a macOS notification comes the day before and on the
  day (once each; the app must be open, and Notifications must be on).
- **Paste a reply** (job window of an application) — for an answer that came on LinkedIn or in a company
  portal. It is filed like an email: one Claude call reads it, or the app's own wording
  rules when the limit is used up. The same text cannot be added twice.
- **Notes about the company** (job window of an application; on a new job only when you already keep notes on that company) — who you spoke to, salary mentioned, what they
  asked, free notes. Kept per company (`data/company_notes.json`, encrypted), so they show
  on every job at that company, also when you apply there again.
- **Compare CV** (job window, when an adapted Word CV exists) — master CV on the left,
  adapted CV on the right, only the paragraphs that differ; replaced words are struck
  through, new words are bold.
- **What the postings pay** (Insights) — every posting in your lists that states pay,
  converted to gross CZK per month (yearly ÷ 12, EUR × 25, USD × 23, rough fixed rates),
  next to your target, with the middle value.
- **Also archived mail and spam** (Options, off by default) — the email scan also reads
  the mailbox's archive ("All Mail") and spam folders, never Sent or Drafts, and still
  read-only. Turn it on if replies get archived by a filter or land in spam.
- **Filtered out · see why** (Last run card) — every posting the last search removed before
  scoring, each with its reason (located in the United States, asks for 6+ years, a word you
  skip, part-time, duplicate, senior title, needs Czech, too old, already applied, closed).
  Filter by reason, search, and open the posting to check a rule. **bring back** adds a posting to New Jobs so
  the next search run scores it (not offered for duplicates, closed postings and roles you already applied for). The list is replaced by
  each search (`data/filtered_out.json`, encrypted, at most 600 rows).
- **Skip levels above yours** and **Skip jobs asking for … years** (Options) — the title
  words that mark a role above your level (senior, lead, manager, …) and the number of years
  of experience from which a posting is skipped (0 = never). Both start from the level in
  your CV: the usual list and 4 years for a junior, 7 for mid, nothing for a senior. Change
  them freely; a title that itself says junior or graduate is never skipped by a level word.
- **Follow-up reminders** — an application still *waiting* with no reply for N days
  (Options → *Remind me after*, default 10, 0 = never; counted from the day you applied,
  the company's last email or your last follow-up; never for applications whose date is
  unknown, and not after 45 days of silence) gets a **follow up** badge and
  is listed first; the sidebar shows how many. In the job view, **Draft follow-up**
  writes a short email for you to **Copy** and send yourself (the app never sends
  mail); **Mark as followed up** restarts the count.
- **Options** — macOS-style settings: city (EU-city picker), job source,
  **search keywords** (add/remove the roles Scout searches for, with suggestions),
  date window, score thresholds, and model. Saved (encrypted) to `data/ui_settings.json`;
  `run.py` and the weekly run use the same saved Options.
- **Welcome screen / Account chip** — the app opens on a short splash, then a
  welcome card showing Claude, job email, master CV and data protection; press
  **Start** (or Enter) to enter. The **Account** chip in the left column reopens the
  same card: a *Sign in with Claude* button, editable Gmail email + App Password
  (the password goes to the macOS Keychain), a CV picker (or drop the file on the
  card) that copies it into `data/cv/`, and an **Approve** button when a protected
  file was changed outside the app (section 10).
- **Status bar and stepper** — while a run is going you see the current step, a
  progress bar with percent and "6 / 14 jobs", and the elapsed time.
- **Weekly run card** — click it to turn the weekly schedule on/off and pick the
  day + time (writes the macOS LaunchAgent for you — see section 9).
- **Usage left** — your 5-hour / 7-day subscription windows; refreshes on open and
  with the **↻ refresh** button.
- Hover any robot for its name, role, and latest result.

Everything it does is the same as the commands below — the window just wraps them.
If you use the app, sections 0, 4, 7 and 9 below are optional (the app covers them).
Section 10 (security) is worth reading once either way.

---

## 2. Run the pipeline (Agents 1→4)

Analyze CV → search jobs → write cover letters → build the Excel tracker.

```bash
python run.py                         # default: Prague, English-only, jobs.cz+prace.cz+LinkedIn
                                      # (if you saved Options in the app, those are the defaults)
```

### Common options (combine freely)

```bash
python run.py --include-remote        # also add RemoteOK + We Work Remotely
python run.py --where Brno            # search a different city
python run.py --threshold 60          # only write letters for stronger matches (default 50)
python run.py --per-query 20          # more results per search query (default 15)
python run.py --max-age-days 14       # how recent a job must be (default 10; 0 = off)
python run.py --reuse-profile         # skip Agent 1, reuse the last CV analysis
python run.py --all-languages         # include Czech-language ads too (default: English only)
python run.py --skip-search           # re-score existing jobs only (no new search)
python run.py --no-tailor-cv          # skip the per-job tailored CVs (letters only)
```

### Choose the job source

```bash
python run.py --source czech          # jobs.cz + prace.cz + LinkedIn + your career sites (default)
python run.py --source linkedin       # LinkedIn only
python run.py --source careers        # your companies' career centers only
python run.py --source remote         # RemoteOK + We Work Remotely only
python run.py --source all            # every configured source
python run.py --source adzuna --where Warsaw   # Adzuna (needs key + ADZUNA_COUNTRY=pl)
```

### Company career centers (data/companies.json)

Pull open roles straight from companies' career sites (added to the default
search automatically once configured). Edit `data/companies.json`:

```json
[
  {"name": "Bloomreach", "ats": "greenhouse", "token": "bloomreach"},
  {"name": "GitLab",     "ats": "greenhouse", "token": "gitlab"},
  {"name": "Acme",       "ats": "lever",      "token": "acme"}
]
```

Supported ATS platforms (public APIs): **greenhouse**, **lever**,
**smartrecruiters**, **recruitee**. `token` is the slug in the career-site URL
(e.g. `boards.greenhouse.io/gitlab` → `gitlab`). See `data/companies.example.json`.

**Not supported:** SAP (jobs.sap.com) and Microsoft careers block scraping. For
those, set up their own **job agent / email alert** on the company site — Agent 5
reads the reply emails into your tracker (`python status.py sync`).

---

## 3. Track applications (Agent 4)

```bash
python status.py list                              # list all tracked jobs + their IDs
python status.py apply <job-id>                     # applied a lead → status 'waiting'
python status.py apply <job-id> --note "sent via LinkedIn"
python status.py update <job-id> interview --note "call Fri 10:00"
python status.py prune                              # drop new_jobs leads you've already applied to
python status.py letters                            # import your own cover letters from ~/Documents/CV/Letter
python status.py rebuild                            # regenerate both Excel files
python status.py followups                          # applications with no reply for N days
python status.py followups --days 21                # ...with a different N
python status.py pdf                                # make missing PDF copies of adapted CVs + app-written letters
python status.py pdf --all                          # remake all of them
```

Valid statuses: `found` · `letter_ready` (leads, in **new_jobs.xlsx**) ·
`waiting` · `interview` · `offer` · `rejected` · `on_hold` (applications, in
**applications.xlsx**).

**Two files:**
- `new_jobs.xlsx` — fresh leads from search you haven't applied to yet. Companies
  you've already applied to or been rejected by are automatically excluded.
- `applications.xlsx` — applications you've sent. Status starts at `waiting`;
  when an email reply arrives, `sync` updates it (interview / rejected / offer)
  and fills the interview-progress path.

When you apply to a lead, run `apply <id>` — it moves from new_jobs.xlsx to
applications.xlsx as `waiting`.

---

## 4. Email responses & rejection analytics (Agent 5)

Reads your inbox **read-only** (never sends/deletes/marks). Needs the job email set
up in the app's **Account** card (see sections 7 and 10).

```bash
python status.py sync                 # scan inbox → update statuses + response DB + reports
python status.py sync --days 10       # only scan the last 10 days (default: IMAP_LOOKBACK_DAYS)
python status.py responses            # show reply / interview / offer / rejection-reason breakdown
python status.py responses --scan     # scan inbox first, then show the report
python status.py repair-emails        # re-read email text (no Claude usage) and fix replies that were
                                      # filed wrongly because the email was HTML only
```

When a reply is matched to a job, its status is updated and the job automatically
moves from new_jobs.xlsx to applications.xlsx. Matching uses the company (from the
sender/subject) plus the role in the subject line, so replies link to the right
posting even when you've applied to several roles at one company.

By default only the Inbox is read. With **Also archived mail and spam** on in Options,
the archive and spam folders are read too (found by their IMAP flags, so the folder
names can be in any language). A reply that never reached your mailbox (LinkedIn, a
company portal) can be pasted in from the job window in the app.

Outputs: `data/responses.db` (database),
`data/excel_reports/responses_report.xlsx` (analytics: Summary / Progress / Responses).

---

## 5. Claude usage / subscription limits

```bash
python status.py usage                # tokens, API-equivalent cost, and real % of
                                      # your 5-hour / 7-day subscription windows used
python status.py usage --reset        # zero the counters
```

For the authoritative subscription limits you can also run `/usage` inside the
Claude Code terminal.

---

## 6. Tests

```bash
pytest                                # run the full offline test suite
pytest -v                             # verbose
pytest tests/test_scrapers.py         # run one test file
```

Tests use no network and no Claude usage (scrapers run against saved fixtures,
the AI is mocked). They work in temporary folders with an in-memory Keychain, so
your real data, `.env` and Keychain are never touched.

---

## 7. Configuration (`.env`)

| Key | What it's for |
|-----|---------------|
| `JOBHELPER_MODEL` | `sonnet` (default) / `opus` / `haiku` |
| `IMAP_USER` | Gmail address for Agent 5 (the **App Password** is in the Keychain, not here) |
| `IMAP_LOOKBACK_DAYS` | How many days of inbox to scan (default 30) |
| `JOOBLE_API_KEY` | Optional Jooble key |
| `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` / `ADZUNA_COUNTRY` | Optional Adzuna (non-Czech) |

**Gmail App Password:** Google Account → Security → 2-Step Verification (on) →
App passwords → create one → enter the 16 letters in the app: **Account** chip →
*Job email* → **Change** → **Save**. It is stored in the macOS Keychain. (If you
ever put `IMAP_PASSWORD=` in `.env`, the next start moves it to the Keychain and
removes the line.) Details in section 10.

---

## 8. Typical weekly flow

```bash
source .venv/bin/activate
python run.py --include-remote        # find new jobs + write cover letters
python status.py list                 # review matches, open the Excel
# ... apply to the good ones, then mark them (moves lead → applications as 'waiting'):
python status.py apply <job-id>
# ... later, after replies arrive:
python status.py sync                 # update statuses + rejection database (auto-moves answered jobs)
python status.py responses            # see why you're getting rejected
python status.py usage                # check how much subscription you've used
```

Or just open the app (`python app_qt.py`) and use **Run search** / **Scan email**.

---

## Files produced

| Path | What |
|------|------|
| `data/excel_new_jobs/new_jobs.xlsx` | Fresh leads from search (not applied yet) |
| `data/excel_applications/applications.xlsx` | Applications you've sent + interview progress |
| `data/excel_reports/responses_report.xlsx` | Rejection / response analytics |
| `data/cover_letters/` | Generated cover letters (`.docx` + `.pdf`) |
| `data/cv/` | Your master CV(s) |
| `data/tailored_cvs/` | Per-application adapted CVs (`.docx` + `.pdf`) |
| `data/responses.db` | Response database (encrypted) |
| `data/jobs.json` | Underlying job database, source of truth (encrypted) |
| `data/profile.json` | Agent 1's CV analysis (encrypted) |
| `data/usage.json` | Claude usage tracker |
| `data/ui_settings.json` | Desktop-app Options: city, source, thresholds, model (encrypted) |
| `data/company_notes.json` | Your notes per company (encrypted) |
| `data/filtered_out.json` | What the last search filtered out, with reasons (encrypted) |
| `data/backups/` | Timestamped backups, encrypted (`*.enc`) |
| `data/vault.json` | Which key this data belongs to (no secret inside) |
| `data/integrity.json` | Signatures for the tamper check |
| `requirements.lock` | Hash-pinned package list |

The encrypted files cannot be opened in a text editor or database viewer; use the
app, `python status.py list` / `responses`, or `python status.py security restore`.

### Regenerate a cover letter + tailored CV on demand

```bash
python status.py retailor            # all qualifying leads missing a letter or adapted CV
python status.py retailor <job-id>   # one specific job (always re-adapts its CV)
python status.py retailor --all      # re-adapt the CV for every qualifying lead
python status.py retailor --all --letters   # ...and rewrite the letters this app generated
```

### How the adapted CV is made

The rules live in `data/cv_adaptation_instruction.md` (edit that file to change
them, then approve the change: section 10). For each job the master `.docx` is copied and only two parts are rewritten:
**PROFILE** and the **KEY SKILLS** rows. Header, Projects, Work Experience,
Education and Languages stay identical, because only `word/document.xml` is edited
and every other file in the package is copied unchanged.

Each result is checked before it is saved: locked paragraphs identical to the
master, no em dashes or emojis, every technology in KEY SKILLS present in the
master, "not yet done" technologies allowed in PROFILE only as an interest, and a
length estimate that it still fits on one page. Files are named
`<Name>_CV_<Company>_<RoleShort>.docx` in `data/tailored_cvs/`.

**PDF copies.** With LibreOffice installed (`/Applications/LibreOffice.app`) every
adapted CV and app-written letter also gets a `.pdf` next to the `.docx`, and the
one-page rule is checked on the rendered page: if the CV comes out longer than one
page, items are dropped from the end of the longest KEY SKILLS row until it fits.
Without LibreOffice nothing breaks; there are simply no PDFs and the one-page
check is an estimate. LibreOffice lays text out slightly differently from Word
(for example the right-aligned dates), so look at a PDF once before sending it.
Your own letters are never converted.

### How the cover letter is made

The rules live in `data/cover_letter_instruction.md`; the look comes from
`data/cover_letter_template.docx` (your Wargaming letter). After editing either
file by hand, approve the change (section 10). Only the title line,
the date and the five body paragraphs get new text; the head block, fonts,
spacing and page setup are untouched (only `word/document.xml` is edited). The
adapted CV is made first and the letter is written to match it.

Checks before a letter is saved: exactly five paragraphs, 320-410 words,
formatting identical to the template once all text is stripped, no em dashes or
emojis, no gap admissions ("not yet", "although", "limited", "lack" ...), and no
technology outside the master CV presented as experience (it may be named as the
employer's platform or as something you want to work with). Files are named
`<Name>_CoverLetter_<Company>_<RoleShort>.docx` in `data/cover_letters/`.
Your own letters in `~/Documents/CV/Letter` are never rewritten.

## 9. Weekly automation (macOS LaunchAgent)

A LaunchAgent runs a **job search + email analysis** every Monday 09:00:
`~/Library/LaunchAgents/com.jobhelper.weeklyscan.plist` → `weekly_jobhelper.sh` →
`run.py --reuse-profile` then `status.py sync --days 10`

Easiest way to change it: click the **Weekly run** card in the app to turn it
on/off and pick the day + time. The commands below do the same by hand:

```bash
launchctl list | grep jobhelper                 # is it registered?
zsh weekly_jobhelper.sh                          # run search + email now (manual)
launchctl unload ~/Library/LaunchAgents/com.jobhelper.weeklyscan.plist   # disable
launchctl load -w ~/Library/LaunchAgents/com.jobhelper.weeklyscan.plist  # re-enable
tail -f data/weekly_jobhelper.log                # watch results
```

Requires: Mac awake + logged in + the Samsung SSD mounted at run time.
The weekly run uses the Options saved in the app. It stops without generating
anything if a protected file was changed and not approved, or if the data key is
missing; the reason is written to `data/weekly_jobhelper.log`.

## Version history and "What changed"

The project is a local git repository (nothing is uploaded anywhere). Everything in
`data/` and the `.env` file stay out of it, so your CV, letters, rules and database are
never part of the history; they are protected by the encrypted backups instead (section 10).

```bash
git log --oneline            # the saved versions, newest first
git status                   # what has changed since the last saved version
git diff                     # the changes themselves
git restore path/to/file     # put one file back to the last saved version
```

`CHANGELOG.md` lists the changes in plain words, newest first. The app shows the same
list in **Help → What changed**. Add a `- ` line under a `## date` heading for each change.

---

## 10. Security: encryption, Keychain and tamper check

What is protected:

- **Gmail app password** is in the macOS **Keychain**, not in `.env` (`.env` keeps only the address).
- **`jobs.json`, `profile.json`, `ui_settings.json`, `responses.db`** and everything in
  **`data/backups/`** are AES-256 encrypted. The key is in the Keychain too.
- **CV rules, cover-letter rules, letter template, master CV, career-site list** are signed.
  If one changes outside the app, the app and the weekly run stop and ask you to approve it.
- CVs, cover letters and Excel trackers stay normal files so Word and Excel can open them.

### Do this once: save your recovery key

```bash
cd /path/to/JobHelper && source .venv/bin/activate && python status.py security recovery-key
```

It prints one line of letters and digits. Copy it into a password manager (or
write it down and keep it somewhere safe). The data key exists only in this Mac's
Keychain: on a new Mac, or after a Keychain reset, this line is the only way to
open your encrypted data and backups. Anyone who has it can read them, so do not
keep it in a file on the Samsung drive. You only need to do this once; the key
does not change.

To use it later (new Mac, or the app says the key is missing):

```bash
python status.py security restore-key   # paste the saved line when asked
```

### When you need "approve" (and when you don't)

You do **not** need to run anything now, and not on a normal day. Approve is only
for the moment after **you** changed one of the five protected files outside the app:

| You did this | What happens | What to do |
|---|---|---|
| Edited `data/cv_adaptation_instruction.md` or `data/cover_letter_instruction.md` in an editor | Welcome card shows "Changed outside the app", Run search and the weekly run refuse to start | Approve |
| Replaced or edited `data/cover_letter_template.docx` | same | Approve |
| Copied a new CV into `data/cv/` in Finder | same | Approve |
| Edited `data/companies.json` by hand | same | Approve |
| Changed the CV with **Change…** in the Account card, or career sites in **Options** | nothing, changes made in the app are trusted | nothing |
| Did not touch these files but the warning appears | something else changed them | open the file and check it **before** approving |

Approve in the app (**Account** chip → **Approve** on the *Data protection* row) or:

```bash
python status.py security approve
```

### All security commands

```bash
python status.py security status        # what is encrypted, is the password in the Keychain, tamper check
python status.py security approve       # accept files you edited by hand
python status.py security recovery-key  # show the data key - save it in a password manager
python status.py security restore-key   # put that key back (new Mac, or the Keychain was reset)
python status.py security backup        # make an encrypted backup of the data files
python status.py security restore data/backups/<backup> ~/Desktop/restored   # decrypt a backup
```

### The Gmail app password on your Mac

- **Where it is:** open the **Keychain Access** app (Spotlight: "Keychain Access"; on newer macOS the
  **Passwords** app does not show these entries), pick the **login** keychain and search for
  **JobHelper**. You will see *JobHelper: Gmail app password* (account `imap_password`) and
  *JobHelper: data encryption key* (account `data_key`). Double-click, tick **Show password**
  and enter your Mac password to see it.
- **How to add or change it:** in the app click the **Account** chip, then **Change** on *Job email*,
  type the address and the 16-letter app password, **Save**. The app writes it to the Keychain.
- **How to get a new app password from Google:** <https://myaccount.google.com/apppasswords>
  (2-Step Verification must be on), create one named "JobHelper", copy the 16 letters.
- **If macOS asks** "security wants to use your confidential information stored in JobHelper",
  enter your Mac password and choose **Always Allow**.
- **Do not delete** *JobHelper: data encryption key*: without it (or the recovery key) the
  encrypted data cannot be opened.

### Hash-pinned packages

```bash
pip install --require-hashes -r requirements.lock   # install exactly the locked, hash-checked packages
python scripts/lock_requirements.py                  # refresh the lock after changing requirements.txt
```
