# JobHelper: the illustrated guide

How to use each part of the app, what it is for, and why it works the way it does.

The pictures show the real window filled with **invented** people and companies. They are made
by a script (`tests/guide_shots.py`), so they can be taken again whenever the window changes:

```bash
pytest tests/guide_shots.py -q -o addopts=""
```

The same guide as one file to read or print: [GUIDE.pdf](GUIDE.pdf) (made with `python scripts/guide_pdf.py`).

Other documents: [README](../README.md) for setup, [COMMANDS](../COMMANDS.md) for every command
and option, [HANDBOOK](../HANDBOOK.md) for the rules the app is built by and what is left to do.

## Contents

1. [What the app does for you](#1-what-the-app-does-for-you)
2. [Before the first run](#2-before-the-first-run)
3. [The main screen](#3-the-main-screen)
4. [Running a search](#4-running-a-search)
5. [New Jobs: choosing what to apply to](#5-new-jobs-choosing-what-to-apply-to)
6. [One job in full](#6-one-job-in-full)
7. [Your documents: the CV, the letter, form answers](#7-your-documents-the-cv-the-letter-form-answers)
8. [When a score cannot be trusted](#8-when-a-score-cannot-be-trusted)
9. [After you applied](#9-after-you-applied)
10. [Replies from companies](#10-replies-from-companies)
11. [Preparing for an interview](#11-preparing-for-an-interview)
12. [Seeing what the app left out](#12-seeing-what-the-app-left-out)
13. [Learning from your results](#13-learning-from-your-results)
14. [Options](#14-options)
15. [The weekly run](#15-the-weekly-run)
16. [Your data and how it is protected](#16-your-data-and-how-it-is-protected)
17. [When something looks wrong](#17-when-something-looks-wrong)

---

## 1. What the app does for you

Looking for a job means doing the same five things over and over: reading postings, deciding
which ones fit, rewriting your CV and a letter for each, keeping a list of where you applied,
and reading the answers. JobHelper does the repetitive part of all five and leaves the
decisions to you.

| Robot | Does | Uses Claude |
|---|---|---|
| **Profiler** | Reads your CV and works out what to search for | once per CV |
| **Scout** | Searches the job boards and filters out what cannot fit | no |
| **Scribe** | Scores each posting against your CV; writes an adapted CV and a letter for the good ones | yes |
| **Tracker** | Keeps the Excel tables up to date | no |
| **Postman** | Reads the replies in your mailbox and updates your applications | for new replies |

**What it never does.** It never applies for you, never sends an email, and never writes
anything in a CV or letter that is not in your own CV or in notes you gave it. You read, you
decide, you send.

**What it costs.** It works through your Claude subscription, so there is no bill per search.
What a search uses counts against your normal Claude limits, and the app shows how much is left.

---

## 2. Before the first run

![The welcome card](img/01_welcome.png)

When the app starts it checks four things and shows them on the welcome card. A search can only
start when all four are green.

| Row | What it is | Why it is needed | If it is red |
|---|---|---|---|
| **Claude account** | The Claude sign-in on this Mac | Scoring and writing are done by Claude | Press **Sign in with Claude**; a browser window opens |
| **Job email** | The mailbox you apply from, opened read-only | So replies update your applications by themselves | Press **Change** and enter the address and a Gmail *App Password* (not your normal password) |
| **Master CV** | Your one true CV, a `.docx`, `.pdf` or `.txt` | Every adapted CV is made from it and may only say what it says | Press **Change…** and pick the file |
| **Data protection** | Encryption of your job data, with the key in the macOS Keychain | Your applications and replies are private | Follow the line of text on the card |

The email row is the only optional one. Without it everything works except reading replies.

**Why an App Password.** It is a separate 16-letter password that only lets a program read
mail, and you can cancel it in your Google account at any time without changing your real one.

**Do this once:** save your recovery key somewhere safe. Without it, your data cannot be opened
on another Mac or after the Keychain is reset.

```bash
python status.py security recovery-key
```

---

## 3. The main screen

![The main screen](img/02_main.png)

**Left column: your lists.**
- **New Jobs**: postings found for you that you have not applied to.
- **Applications**: where you applied, and where each one stands. A line under it says when
  something needs you ("1 to follow up").
- **Responses**: every reply email the app has read.
- **Analytics** and **Insights**: numbers about your search (sections 10 and 13).
- **Account**: the chip opens the card from section 2 again. The three dots under it are the
  same checks at a glance.
- **Search**: what the next search is set to. Click a chip to change it in Options.

**Middle: the assembly line.** Each robot lights up while it works and shows a tick when it is
done. The line under it always says what is happening or what just happened. **Run search** and
**Scan email** start the two kinds of run; the sun button switches between dark and light.

**Right column: where you stand.**
- **Usage left**: how much of your Claude limit remains in the current 5-hour and 7-day windows.
- **Last run**: what the last search found, how many postings it filtered out (click to see
  why), how many letters and CVs it wrote, and when the mailbox was last read. *Same work via
  API* is what that work would have cost on the paid API; you paid nothing extra.
- **Coming up**: the next dated event, such as an interview.
- **Weekly run**, **Options**, **Help**.

---

## 4. Running a search

Press **Run search**.

![A search in progress](img/03_running.png)

What happens, in order:

1. **Profiler** reads your CV (only if it changed since last time).
2. **Scout** asks the job boards for each of your search roles in your city, then drops what
   cannot fit: postings in a language you did not ask for, titles above your level, part-time
   work if you want full-time, postings older than your limit, roles you already applied to.
   Every dropped posting is kept with its reason (section 12).
3. **Scribe** scores what is left, five postings per Claude call. For each one at or above your
   limit it writes an adapted CV and a cover letter.
4. **Tracker** rebuilds the Excel tables.

The status line shows the step, a percentage and the time. The button becomes **Stop**: it
stops after the step in progress, and everything finished before that is kept.

**If Claude's limit runs out** during a search, the run pauses instead of failing. A window
tells you when the limit resets, and **Resume** continues from where it stopped.

**Why some postings are skipped before scoring.** Scoring costs a Claude call. A posting whose
title is plainly another profession, another language, or far above your level is marked
*skipped* for free. You can always send one to scoring yourself.

A search also quietly looks after the list: postings that came back empty are read once more,
and earlier postings are asked whether they still accept applications.

---

## 5. New Jobs: choosing what to apply to

![The New Jobs list](img/04_new_jobs.png)

Each row is one posting, best score first.

| You see | It means |
|---|---|
| The number on the left | The score, 0 to 100: how well the posting fits your CV and the roles you want |
| **was 64** under it | What it scored before it was scored again |
| **strong / moderate** | 60 or more / 50 to 59. Both got a CV and a letter |
| no badge | Below your limit. Listed so you can judge for yourself; no documents were written |
| **skipped** | Not scored at all (see section 4) |
| The grey line | When it was posted, a salary estimate, and any warning about the score |

The buttons on a row open the posting, the letter and the CV. **mark applied** moves the job to
Applications; press it after you really sent the application.

The chips under the search box filter the list. **Score all again** scores every job with your
current Options (it asks first, because it uses your Claude limit).

**Click a row** to see the job in full.

---

## 6. One job in full

![The job window](img/06_job_window.png)

**Before you apply** is a checklist for this one job: read the posting, check the CV, check the
letter, draft the form answers. Tick the steps as you go; the ticks are remembered. The buttons
on the right open each thing, and **Show in folder** selects the file in Finder so you can drag
it into an application form.

**Why this score** is the reason in words. Read it before applying to anything below "strong":
it tells you what the posting asks for that your CV does not show.

![The score and the keywords](img/07_job_score_keywords.png)

**Keywords in the posting** compares the skills and tools the posting names with your CV.
*Not in your CV* is information for you: something to learn, or something you know but forgot
to write down. The app never adds such a word to an adapted CV.

At the bottom: **Form answers**, **Not interested** (removes the job; its documents go to a
backup), and **Mark applied**.

---

## 7. Your documents: the CV, the letter, form answers

### The adapted CV

For each good posting the app makes a copy of your CV in which the profile paragraph and the
skills list are reworded and reordered to put first what this posting asks for. Everything
else stays as you wrote it.

![Master CV next to the adapted one](img/09_compare_cv.png)

**Compare CV** shows exactly what changed, side by side: your master CV on the left, the
adapted one on the right, new words in bold. Use it to check that nothing was stretched.

### The cover letter

The letter is written to the company, about this role, from the facts in your CV. **Edit
letter** opens it paragraph by paragraph: change the words yourself, or ask for one paragraph
to be rewritten with a hint such as "shorter". The head, date, greeting and layout stay as they
are.

A letter **you** wrote is never touched. Put it in the folder under Options → *Your own
letters*, named after the company, and the app uses it instead of writing one.

### Form answers

Application forms ask their own questions, and every form asks different ones.

![Answers for one job's form](img/10_form_answers.png)

Paste that form's questions, one per line, and press **Draft**. The answers come from your CV
and the posting. An answer the app cannot give truthfully (a salary figure, a date) is left
with a marker and a **Check** note, so you fill it in yourself. The answers are kept with the
job.

---

## 8. When a score cannot be trusted

Two situations make a score misleading, and the app marks both.

### The posting could not be read

Some job boards return only a title or a short summary. The row then says **scored from the
title only** or **scored from a short summary**. A title-only score is capped at 40 and gets no
documents, because a letter written from a title could only be generic.

In the job window, **Read it again** tries the board once more, and **Paste the posting's
text** lets you copy the text in from your browser. Either way the job is then scored again by
itself.

### The score dropped after documents were written

If you tighten your Options and score again, a job that had a letter and CV can fall below your
limit. Its row says **documents from a higher score**.

![A job that fell below the limit](img/08_job_below_limit.png)

**Move documents to backup** puts the letter and CV the app wrote into an encrypted backup. The
job stays in the list. **Put them back** returns them.

![Moving documents for several jobs at once](img/05_move_documents.png)

New Jobs can do it for all such jobs at once. It names the jobs and asks first, and offers
**Put them back** for a week afterwards.

**Why not just delete them.** You may have had a reason to apply anyway. Nothing the app wrote
for you is thrown away without a way back.

---

## 9. After you applied

![The Applications list](img/11_applications.png)

Applications are grouped by where they stand: offers and interviews first, then waiting, then rejected.

![An application in full](img/12_application_window.png)

- **Status**: normally set by the replies in your mailbox. Change it by hand when the news came
  another way.
- **Applied on**: the day you applied. Correct it if you applied before you pressed the button.
- **A date to remember**: an interview, a deadline, a test task, a call. It shows on the main
  screen, and you get a notification the day before and on the day (with a time: also about
  three hours and one hour before). **Add to calendar** puts it in Calendar so your phone
  reminds you too.

![Dates, pasted replies and notes](img/13_application_dates_notes.png)

- **Paste a reply**: an answer that came on LinkedIn or in a company portal can be pasted in
  and is filed like an email.
- **Notes about the company** are kept for the company, not the job: who you spoke to, the
  salary mentioned, what they asked. They appear again when you apply there later.
- **Follow-up**: after ten quiet days the app suggests a follow-up and drafts one to copy. It
  does not send it.

---

## 10. Replies from companies

Press **Scan email**. Postman reads new mail in the mailbox, works out which messages are
answers to your applications, and files each one to its application. It only reads: nothing is
sent, deleted or marked as read.

![Every reply](img/15_responses.png)

**Responses** lists every reply with what it was: an invitation, a rejection, an offer, or an
automatic confirmation. Click one to read it in full.

![Outcomes and rejection reasons](img/16_analytics.png)

**Analytics** adds them up: what happened in the last seven days, how many applications are
waiting, in interviews or closed, and what reasons the rejections gave. The reasons are the
useful part: if most of them say the same thing, that is what to change.

---

## 11. Preparing for an interview

![The interview preparation](img/14_interview_preparation.png)

In an application's window, **Interview preparation** builds a sheet for that one interview:
what to expect, questions an HR person is likely to ask (answered in plain words) and questions
an engineer is likely to ask (answered precisely), a short opening pitch, and questions you can
ask them.

The answers are a starting point built from your CV. An answer that touches something your CV
does not show is marked **Check this answer**, so you never repeat a claim you cannot back.

**Edit** lets you rewrite any part in your own words; **Open as document** makes a Word sheet
to print or read on the way.

After the interview the window offers a short **thank-you** note to copy.

---

## 12. Seeing what the app left out

A search that only shows you what it kept would be asking you to trust it blindly.

![Postings the last search filtered out](img/17_filtered_out.png)

**Filtered out** (click the number on the Last run card) lists every posting the last search
dropped, with the reason for each. The chips group them by reason. If a rule dropped something
you wanted, **bring back** puts it in New Jobs for the next search to score, and Options is
where you change the rule.

---

## 13. Learning from your results

![Insights](img/18_insights.png)

**Insights** is worked out on your Mac from your own applications, with no Claude call:

- **What is working**: which kinds of role and which job boards led to interviews.
- **Week by week**: how many applications you sent and what came back.
- **Skills to learn**: what the postings ask for most that your CV does not show.
- **What the postings pay**, where they say.
- **How long companies take to answer.**
- **Why jobs scored low**: the reasons that come up most often.

With only a few applications the app says "too few to say" rather than guessing.

---

## 14. Options

![Options: the search](img/19_options_search.png)

Options is where you tell the app what you are looking for. The most important settings:

| Setting | What it does | Why you would change it |
|---|---|---|
| **City** | Where to search | The app will not search without one |
| **Source** | Which job boards | More sources find more, and take longer |
| **English only** | Drops postings written in another language | Turn off if you also work in the local language |
| **Search roles** | The words typed into the job boards | Too few results: add a role. Too many poor ones: remove one |
| **Write letters above** | The score from which a CV and letter are written | Raise it to apply to fewer, better matches |
| **Skip titles with / but keep** | Words that drop a posting by its title, and exceptions | To get rid of a kind of posting that keeps appearing |

![Options: the roles you want and your profession](img/20_options_roles.png)

**Kinds of role you want** tells the scorer your direction. Without it, a role in another field
that merely accepts your degree could score high. **Kinds of role you do not want** are skipped
when the title names one, and scored low otherwise.

**Your profession** is shown under the roles. The app reads it from the roles you want (the
outlined chip), and it decides which titles are skipped as "another profession" before scoring.
If the app read it wrong, click the right chips yourself; **Let the app decide** goes back.

**Skip levels above yours** and **Skip jobs asking for … years** keep out postings you are not
yet eligible for. A senior candidate empties the level list.

**About you** (right to work, when you can start) and **More about your work** give the app
true facts to use in letters and answers that are not in your CV.

![Options: notifications and storage](img/21_options_storage.png)

**Keep backups** is how many automatic backups are kept. **Moved documents older than … days**
removes old copies from the backup after asking; they go to the Trash, never straight to
deletion.

Closing Options with unsaved changes asks first.

---

## 15. The weekly run

![The weekly run](img/22_weekly_run.png)

Pick a day and a time, and macOS runs a search and an email scan for you once a week, even with
the window closed. You get a notification when it is done. If the Mac is asleep at that time, the run
happens when it wakes; if it is switched off, that week's run is skipped.

---

## 16. Your data and how it is protected

- **Everything stays on your Mac.** The only things that leave it are the questions put to
  Claude (your CV text and a posting) and the requests to the job boards and your mailbox.
- **Encrypted on disk**: the job list, your profile, your settings, the replies and all backups.
- **In the macOS Keychain**: the Gmail app password and the key to the encrypted files.
- **Ordinary files** on purpose: the CVs, letters and Excel tables, so Word and Excel can open
  them. An encrypted disk is what protects those.
- **Backups** are made automatically before the app changes data in bulk.
- **Signed rule files**: if the files that tell the app how to write your CV and letters are
  changed outside the app, it asks you to approve the change before the next run.

---

## 17. When something looks wrong

![Help inside the app](img/23_help.png)

**Help** in the app covers the same ground as this guide in short form, and its second tab
lists what changed in each version.

| What you see | What to do |
|---|---|
| A button does nothing | Open the Account chip and check the four rows are green |
| A red line at the top of the main screen | The start-up check found something; the line says what and how to fix it |
| No results | Check the city and the search roles in Options; look at **Filtered out** to see what was dropped and why |
| Too many poor jobs | Add words to *Skip titles with*, set *Kinds of role you want*, or raise *Write letters above* |
| Good jobs are skipped | Check the profession chips in Options; use **Score it anyway** on a single job |
| A score looks wrong | Read *Why this score*; if the row says it was scored from little text, see section 8 |
| A rejection is missing | It probably did not arrive in the scanned mailbox. Set the status by hand, or paste the reply |
| The search paused | Claude's limit ran out. The window says when it resets; press **Resume** then |
| Something failed quietly | `data/app_trouble.log` has one line for each error the app carried on after |

![The light theme](img/24_light_theme.png)

The sun button at the top switches between the dark and the light theme.
