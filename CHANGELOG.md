# What changed

The newest changes are first. The Help window in the app shows this file under "What changed".
Format: a `## date` line, then one `- ` line per change; `**words**` are shown in bold.

## 8 October 2026

- **Clear messages for wrong steps in Form answers**: unusable pasted text, too many questions, replacing answers, closing with unsaved changes and copying an unfinished answer are each explained in red, and nothing is cut or lost silently.
- **Messages on top of open windows**: a result or an error that used to appear only in the status line behind a window now also shows above it, in red when something went wrong.
- **Form answers, per job**: the general Answers window is replaced. Paste the questions of a job's application form and Claude drafts the answers for that job from your CV and the posting; they are kept with the job, and what it cannot know is marked for you.
- **Back up everything**: `python status.py security backup-all` writes one encrypted backup with the app's data and your documents (master CV, your own letters, the app's letters and CVs, rule files, template).
- **Smoother list on the left**: moving the mouse quickly no longer leaves a dark shadow on the row you left.
- **Insights opens at once**: the slow part is prepared in the background when the app starts.
- **No built-in city**: the search uses the city from Options; a new user is asked to choose one before the first search.
- **Cities outside Czechia** are sent to LinkedIn as written (Vienna is no longer searched as "Vienna, Czechia").
- **Your own letters live in the app's folder**: `data/my_letters/`, with an Open folder button in Options. The app can open them and never changes them.
- **Own letters are matched to the right company**: one shared word ("Data") no longer links a letter to another company, and a letter already on a job never creates a second application.
- **Weekly run works from any folder**: the weekly script finds the project by its own location and takes the scan period from Options, so nothing in it is tied to one computer.
- **Before you apply**: a checklist at the top of a new job's window (posting, CV, letter, one PDF, answers) that remembers what you have done, ending with Mark applied.
- **One PDF**: the letter followed by the CV as a single file, for forms that take only one.
- **Reminders by the hour**: a date with a time is also announced about three hours and one hour before.
- **Upkeep**: the window's code is split into one file per window (no visible change), so later changes are safer.
- **Start-up check**: when the app opens it checks that your data opens, the rules are unchanged, the CV and template are there and Claude is signed in. You see one line only when something is wrong.
- **Restore test**: `python status.py security test-restore` makes a backup, restores it into a temporary folder and compares it with the live data, then checks that every older backup can still be decrypted.
- **Week by week** in Insights: applications sent and replies received each week.
- **How long companies take to decide**: days from applying to the first rejection or invitation, and which waiting applications are past that point.
- **Why jobs score low**: what the explanations of low scores mention most (missing technology, more experience, another field, another language).

## 7 October 2026

- **Add to calendar**: a date to remember can be opened as a calendar file, so Calendar (and your phone) reminds you when the app is closed.
- **Thank-you draft**: on and after the day of an interview or call, the job window offers a short note to copy and send yourself.
- **The last 7 days**: Analytics starts with new jobs, replies, follow-ups due and dates coming up; the weekly run sends the same as one notification.
- **Bring back**: a posting in the filtered-out list can be added to New Jobs with one button; the next search run scores it.
- **English ads are no longer mistaken for Czech**: a long English posting with a few Czech letters (a bank or city name) was removed as "written in Czech"; 12 such postings were lost in one search.
- **Years that are only a wish** ("5 years is an advantage") no longer count as a requirement.
- **Levels and years in Options**: the title words that mark a role above your level, and the number of years from which a posting is skipped, are now edited in Options. They start from the level in your CV.
- **Filtered out · see why**: the Last run card lists every posting the last search removed before scoring, each with its reason.
- **"Management" is no longer a senior word**: titles like "Repository Management" were removed by mistake; a title that says junior or graduate is never removed as senior.
- **A date to remember**: put an interview, deadline, test task or call on an application. It shows under Coming up, with a notification the day before and on the day.
- **Paste a reply**: an answer from LinkedIn or a company portal can be filed like an email.
- **Notes about the company**: who you spoke to, salary mentioned, what they asked. Kept per company.
- **Compare CV**: master CV next to the adapted one, only the paragraphs that differ, with a note when the CV was adapted from an earlier master.
- **What the postings pay**: a new section in Insights, next to your target.
- **Also archived mail and spam**: an Options switch that widens the email scan beyond the Inbox.
- **Old-format letters** are labelled in the job window and open in Word.
- **Version history**: the project is now kept in a local git repository; your data folder stays out of it.

## 6 October 2026

- **Help window** with key words in bold, and clearer wording for the cost rows.
- **Notifications** when a search or scan finishes, pauses on the limit, or finds an interview invitation.
- **Backup and log clean-up**: only the newest backups are kept (Options, Keep backups).
- **Interview preparation**: likely questions with answers built from your CV.
- **Insights**: which kinds of role and which search keywords work, and skills worth learning.
- **Edit letter**: change a letter the app wrote, or have one paragraph rewritten.
- **Not interested**: remove a job for good, with a filter to bring it back.
- **Search, filter and sort** in every list; responses open in their own window.
- **Skip words and exceptions** for job titles in Options.
- **Second mailbox**, **merge duplicate applications**, and status and apply date set by hand.
- **Pause on the limit**: the run stops at 99%, saves, and continues with Resume when the limit is back.
- **Less limit used**: a free pre-filter for other professions, and five postings per scoring call.
- **Full-time only**, letters from score 30, and a setting for how many days of email to scan.

## Earlier

- **Encryption**: job data and backups are encrypted, secrets are in the macOS Keychain, and changed rule files are detected.
- **Job window**, follow-up reminders with a draft to copy, a Stop button, and PDF copies of CVs and letters.
- **Welcome screen**, account chip, status bar with progress, and the redesigned robots.
