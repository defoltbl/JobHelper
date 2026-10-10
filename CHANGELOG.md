# What changed

The newest changes are first. The Help window in the app shows this file under "What changed".
Format: a `## date` line, then one `- ` line per change; `**words**` are shown in bold.

## 10 October 2026

- **My details takes everything a long form asks for.** Any number of jobs, each with its dates and a switch for a job that goes on (several may be current), and any number of degrees; **Read from my CV** has Claude copy them from your CV for you to check. A form with a row per job or per degree is filled in row by row, your current job first.
- **Salary expectation is a figure with its currency** (CZK, EUR, USD, GBP and nine more), per month or per year.
- **Files for forms:** add certificates, diplomas and references under My details. After a fill they are shown in Finder with the CV and letter, ready to drag onto the form.
- **New page: My answers.** Answer once the questions every form asks (when you can start, your strengths, why you are looking). **Draft with Claude** writes a first version from your CV; once you save it, every form that asks gets your wording with no Claude call. A question about one company is still drafted for each job.
- **Fixed: a text field kept its outline and cursor after you clicked somewhere else.** In the assistant's window, and in the windows of a job, a letter, form answers, the interview sheet, a reply and the lists, a press on empty space now ends the editing of the field, as it already did in Options.
- **The assistant chooses from lists, yes/no buttons and menus.** When your details, the job or your CV settle the answer (your country and city, your notice period, the country code of your phone, where you found the posting, your right to work, years of experience with a tool), it picks the entry and marks it amber for you to check. It opens menus that sites draw themselves, reads their entries and presses the right one. When nothing settles a question, it is left to you. It still never presses a button and never sends a form.
- **The assistant remembers your own wording.** Rewrite an answer on the page and select **Remember what I changed on the page**, or rewrite it under **Form answers**: the next form that asks the same question gets your wording, with no Claude call. An answer that names its company is not used for another one. **My details** shows how many are remembered and can forget them.
- **After a fill the assistant offers what comes next:** **Show my CV and letter in Finder** (to drag onto the form), **Mark applied**, **Fill in this page too** when the form moved on to its next page, and **Open the form in its own tab** when the form sits in a frame from another site.
- **You can ask the assistant a question** about a job or the app, such as "why did this score 62?". Choose the job first; Claude answers in one call from what the app knows.
- **More in My details:** current employer and job title, university and degree, notice period, salary expectation. Forms that ask for them are filled in without a draft.
- **The assistant looks at the pointer** while it is over the assembly line, nods when a request worked and shakes its head when it did not.
- **The assistant chooses your country from a list however the list spells it** ("Czech Republic" for Czechia), leaves boxes that open a menu of their own to you instead of typing into them, and gives a phone field that is too short for the spaces the number without them.
- **Fixed: the assistant's speech bubble jumped as it disappeared.** When the greeting ended, the words changed while the bubble was still fading, so it changed size on its way out. It now keeps its words until it is gone.
- **New: an assistant that fills in application forms.** A light-blue robot stands at the end of the assembly line; it blinks, and waves when the app opens. Open a company's application form in Google Chrome, select the robot and ask it to fill in the form: it writes your name, contacts and links from the new **My details** page and drafts answers to the form's open questions from your CV, for the job the page belongs to. Filled fields are outlined in green on the page, answers to check in amber, and the window lists what was left for you and why. It writes into empty fields only, leaves files, passwords, tick boxes and personal questions to you, and never sends the form. Chrome needs one switch first: **View** > **Developer** > **Allow JavaScript from Apple Events**. A job's window has a new **Fill form in Chrome** button.
- **The user guide and the technical documentation are laid out like a thesis.** Figures and tables are numbered inside their chapter ("Figure 4.2 – Title" under a picture, "Table 4.2 – Title" above a table), the contents lead to each page number with a dotted line, the page number stands at the top right, and the lists of figures and tables at the beginning are gone. The README is rewritten for the app as it is now.
Found by checking all the code again before the next big step.

- **Fixed: a place whose name begins like a country was taken for that country** ("Indianapolis, Indiana" was read as India), so a search in the United States lost postings of its own. Country names are now matched as whole words.
- The weekly schedule can no longer hang while it waits for macOS: its two calls have a time limit.
- **Fixed: a used-up limit filled the log of problems.** Every refresh of the usage card while the limit was used up wrote a line there; it is what the card shows, not a problem.
- **A reply you file by hand is listed under that application's company** when the reader had named another (a video-call service, a recruiting system).
- The command reference (`COMMANDS.md`) was read through and brought up to date: any mailbox instead of Gmail only, the recovery key in the app, the new buttons, pay in your currency.
- Removed what nothing used any more: three functions of the window's back end (the old ways of saving a mailbox and of reading the connections), one language helper, and a second copy of the function that strips HTML from a posting.

- **Review jobs one by one.** In New Jobs, narrow the list (a chip such as *stretch*, or the search box) and select **Review these … one by one**. One window walks through them: **Not interested** or **Mark applied** decides and brings the next job by itself, **Next ›** leaves a job as it is. A bar says where you are and how many you decided.
- **Cover letters get the same check as adapted CVs.** A two-word term of the posting that the letter states as something you did, while your CV has neither word, is sent back to be rewritten; what is still there is named in the job window (**Check your cover letter**). The letter may still speak of the role's terms and of what you want to do. Measured on the 53 letters already written: 4 would have been sent back once.
- Everyday phrases ("attention to detail", "end to end", "version control") are not treated as claims by either check.
- **No Russian services.** Two Russian mail providers had been added to the list of recognised mailboxes; they are removed. The app refuses a mailbox or a mail server of a Russian service and says so.
- **Fixed: error lines in the terminal when the app closed** ("Cannot call method … of null"). The window is now taken down before the part it talks to.
- **Last run card:** the row about the scan's mail reads "1224 · 43 asked" and stays on one line.
- **The adapted CV is checked for the posting's own words, in any profession.** A whole run with an invented accountant's CV on real postings showed the gap: the adapted profile said "coding tax and cost center data" and "vendor master data upkeep", which were the posting's words and not the CV's. The existing check knew technology names only. Now any two-word term of the posting that the draft states as experience, while your CV has neither word, is sent back to be removed or named only as an interest. What is still there after that is not cut out silently: the job window says **Check your adapted CV** and names the terms. On the same postings the new profiles state only what the CV shows.
- **Fixed: a reply could be filed under a company because of a job-title word in the company's name** ("Reed Specialist Recruitment" got a rejection for an "IT Support Specialist" role elsewhere). Such words no longer count as the company's name.
- **Fixed: a long company name in Options → Company career sites ran under the ✕.** It wraps now. Three "too long" messages and the hint under the lists wrap as well.
- **A salary of its own for a kind of role** (Options → About you → **A different figure for**): enter *support* and a figure, and jobs with that word in the title use it instead of the general one, in form answers, the lists and Insights.
- **Test a connected mailbox** (Account card → **Test**): the app signs in once and says whether the mailbox can still be read. More providers are recognised by the address (T-Online, Posteo, mailbox.org, Orange, Libero, Onet), and Tuta is named as one that cannot be read.
- **The PDFs have less empty space:** a chapter now follows on the same page instead of starting a new one. The page rules are unchanged.
- **File a reply under the right application.** In a reply's window, **File under…** lists your applications (type a company or a role to narrow it); choose one and the reply moves there. The application it moves to follows the reply (an invitation makes it an interview, a rejection closes it); the one it leaves keeps its status, which only you can judge. **It belongs to none of my applications** unlinks it.
- **Write CV and letter for one job** (job window): for a job the search wrote no documents for, because it was below your limit or was scored again since. A letter of your own is never replaced; only what is missing is written.
- **Help has a third tab, Usage and problems:** everything the app has asked Claude so far, in all and by kind of work, with what it would have cost through the paid API; and the last problems the app carried on after, with **Show the file in Finder**.
- **See what changed before you approve.** When a rule file, the letter template or the master CV was changed outside the app, the Account card now shows the lines that were removed and added. The app keeps the text of each file as it was when you approved it.
- **Backups from the window** (Options → Notifications and storage): **Back up now** makes one encrypted backup of everything, **Check backups** proves that a backup can be restored, and **Save a readable copy…** puts the newest full backup, not encrypted, into an empty folder you choose.
- **Technical documentation: a chapter on the tech stack** (`docs/CODE.md`, chapter 2). It names every part the app is built from (Python, Qt Quick, the Claude Code program, Word and Excel libraries, SQLite, the Keychain and the rest), what each is used for and **why it was chosen**, and what was deliberately left out.
- **The user guide no longer needs the terminal.** It is written for someone who only uses the app: every command was taken out of `docs/GUIDE.md`. What used to need a command can now be done in the window: the **Account** card shows your **Recovery key** (with **Copy**; it is put away again after a minute), and on a new Mac you paste the key there and select **Open my data**.
- **A separate technical documentation** (`docs/CODE.md`, `docs/CODE.pdf`) for people who work with the code: installing, the command line, the structure of the code, the data files, tests, and how the documentation is made.
- **Both PDFs are laid out like a thesis**: a title page, contents with page numbers, a list of figures and a list of tables, a page number on every page, each chapter on a new page. **A picture is never split across two pages. A table stays on one page**; a table longer than a page continues between two rows, with the caption "continued" and its heading row repeated. A heading is never left alone at the bottom of a page.
- **Every figure and table has a number and a caption, and the text refers to it** ("Figure 5", "Table 12"). The guide has 33 figures and 52 tables.
- **The documents follow one set of writing rules**: headings that name the task, *Overview* and *Prerequisites*, numbered steps, buttons in bold as the app writes them.
- **Documents moved to the backup can be put back for an application too.** When a reply shows that you had applied to a job whose documents were moved (because its score fell), **Put them back** is offered in that application's window; before, it was offered for new jobs only.
- **Interview preparation for any profession.** The second group of questions was written for "an engineer" about "the stack"; it is now for "someone who does this work or the hiring manager", about the specialist side of the role whatever the profession, and the first group avoids the jargon of your field rather than "the technology".
- **Remote jobs by profession.** With "Include remote jobs" on, We Work Remotely was read from its programming lists only. The app now reads the lists of your profession (support, sales and marketing, design, finance and management, or the general ones), and the programming lists as before for software.
- **Any mailbox, not only Gmail.** The Account card recognises Gmail, Yahoo, iCloud, Fastmail, Zoho, AOL, Seznam, GMX, WEB.DE and others by the address, says which server it reads from and what kind of password that provider wants, and asks for the **IMAP server** when it does not know the provider. The 16-letter rule now applies to Google addresses only. The two mailboxes can be at different providers. For Outlook.com, Hotmail and Proton Mail, which cannot be read with a password, the card says so at once and what to do instead.
- **Salary you ask for** (Options → About you): your own figure, gross per month, in your currency (CZK, EUR, USD, GBP, CHF, PLN and others). Form answers give it as your expectation, the job window and the lists show it, the Excel table carries it, and Insights converts what postings pay into the same currency to compare. Before, the app always used its own table of junior software pay in Prague, in crowns: also for a nurse, and also for a search in Berlin. That estimate is now used only when you gave no figure, only for software roles and only in Czechia; anywhere else no figure is shown rather than a wrong one.
- **"Here" is no longer always Prague.** For company career sites and remote jobs the app used to keep anything in Prague or Czechia whatever city you searched, and drop the jobs of your own country. It now keeps your city, your country (it knows the larger cities of about forty countries), the region that country is in ("Europe", "EMEA") and remote jobs that are not tied to another part of the world. New in Options: **Country**, empty by default and read from the city; type it for a city the app does not know. A search in the United States keeps American postings.
- **"English only" now knows other languages than Czech.** An ad written in German, Polish, French, Spanish, Italian, Dutch, Portuguese, Slovak, Russian, Ukrainian or another script is recognised and left out, and the reason names the language ("The ad is written in German") instead of always saying Czech. German and Polish ads used to pass as English. A role that requires any other language at a working level ("fluent German", "Czech or Slovak") is left out too, before it costs a Claude call. In the Filtered out list the group is called **other language**.
- **Replies are matched to the right company more often.** A reply is no longer tied to a company because both names contain a common word ("Solutions", "Global", "Services"); one of the company's own name words must be in the message. On 150 days of real mail, 8 replies that pointed at the wrong company now point at the right one, and no correct match was lost.
- **Last run card: "Emails read"** says how many messages the scan went through and how many of them were sent to Claude ("45 · 5 asked"), so a "0 new" explains itself. The line after a scan says it too.
- **Look further back once** (Options → Email scan): one scan over a longer period, started with **Scan now**; the saved number of days stays as it is. For a newly added mailbox or a missing old reply.
- **A mailbox is tried before it is saved.** Saving the job email or the second mailbox now signs in once with what you entered (the button says **Checking…**). A refused App Password is not saved and the card says so; before, only its form was checked and a wrong one showed up at the first scan. With no connection it is saved, with a note that it was not tried.
- **The usage card corrects itself** when a limit's reset time passes, without pressing refresh.
- **A long choice in a drop-down box** is shown on two lines instead of being cut.
- **Mark applied** and **Not interested** in the job window ask once when text there is not saved, as the ✕ and Esc already did.
- **The guide was rewritten in the style of product documentation** (`docs/GUIDE.md` and `docs/GUIDE.pdf`, 52 pages, 33 pictures): every section now has what the feature is for, **numbered steps**, a **table of every control**, **Note / Tip / Important / Warning** boxes, an "if something is wrong" table and next steps. New: a full **Options reference**, a section on **Claude usage and limits**, how the email scan chooses messages, the second mailbox, a troubleshooting section by topic and a quick reference. Nine new pictures (the list on the left, usage and the last run, a used-up limit, the limit warning, the start-up check, the letter editor, one reply, About you, the email settings).
- **Usage card:** the time a nearly used limit resets is on its own line under the bar, so the card keeps its width.
- **Fixed: the usage card said "13% left" while Claude was refusing for a used-up limit.** It kept showing the numbers from the last answer. A refusal now fills the limit it names ("session limit" is the **5-hour** one, "weekly limit" the **7-day** one), the card says **0% left** in red with the time it **resets**, and a limit whose reset time has passed is shown as free again. The pause message used to name the wrong limit in this case; it names the right one now.
- **Last run card: the API price is the cost of the last run only**, no longer the total of everything since the first day. The row is named after the run: **Same search via API** or **Same scan via API**. **"You paid"** says *subscription only*.
- **Fixed: the welcome animation stuttered.** The app was preparing the **Insights** view at the same moment, which held the window up for about half a second. That preparation now waits until the welcome screen is closed and works in small steps, so nothing on screen is held up (measured: 733 ms of hold-ups at start before, 30 ms now).
- **New icons in the list on the left:** a small **bar chart** for **Analytics** and a **light bulb** for **Insights**, drawn by the app so they are clear in both themes.
- **Email scan asks Claude about far fewer messages.** Adverts and newsletters used to be sent to Claude when they shared one common word with a company you track ("International", "Praha") or mentioned a brand somewhere in the text. Now the sender or the subject must name the company by its real name, automatic mail from that company needs to talk about an application, and job-board alerts and sign-up mail are left out. On 150 days of real mail: **242 messages instead of 661**, and every one of the 133 filed replies still gets through.

- **The guide as a PDF** (`docs/GUIDE.pdf`, 24 pages): the same text and pictures in one file to read or print.

Found by reading all the code line by line.

- **Fixed: a second search in the same app session reused the first one's answers** from the company career sites and the remote boards. Every search now reads them afresh.
- **Fixed: a newly chosen master CV could be ignored** when an older CV in the folder came first by name. The app now remembers the file you chose.
- **The job window asks before closing with unsaved text** (a pasted posting or reply, company notes, a date), on both ✕ and Esc.
- **Options and email addresses are checked by the backend as well as the window**, so nothing unusable can be saved whatever sends it; text that is too long is refused, not cut.
- **Fixed: two companies were taken for one when their names shared any word.** "Accenture Czech Republic" and "PwC Czech Republic" share "Republic", so applying to a role at one could hide the same role at the other as "already applied", and a reply from one could be counted for the other. Names now match only when they are equal, share a real name word, or one is the other with more added. On your data 62 pairs of different companies are now told apart, and the 28 pairs that are one company still match.
- **Fixed: an adapted CV could lose a whole section.** The skills rows were taken to end only at four fixed headings. In a CV whose next section was called anything else (for example "EXPERIENCE"), that section counted as skill rows and was replaced. The rows now end at the next heading of any name, more heading names are recognised ("SUMMARY", "SKILLS" …), and a check fails the file if any section of the master is missing. Your own CV is read exactly as before.
- **A Word CV without a profile section** now gets the short profile note instead of no adapted CV at all.
- **Search roles outside software can be added in Options.** "registered nurse" used to be refused as "not a job role"; a role the app does not know is now asked about once and then added.
- **Insights names the profession** of a role instead of "Other" where it knows it.
- **A document the app replaces is kept in the backup** before the old file is removed.
- **Fixed: the paid API was only refused by the Run buttons.** The command line only warned, and form answers, scoring again, interview preparation and pasted replies did not check at all. Now nothing is ever asked while `ANTHROPIC_API_KEY` is set, whatever started it.
- **Fixed: a false alarm at start-up** when the optional rule files or the letter template are absent. They are optional; the app writes with its built-in rules and a plain letter.
- **Fixed: a search that ended on an unexpected error lost what it had scored**; it is saved now, and the reason is written to `data/app_trouble.log`.
- **Fixed: a company known only from an unclear email got a status no list shows.** Such jobs are now "waiting"; the start-up check reports any job in that state, and `python status.py repair-statuses` fixes them.
- **Safer:** only web links are opened from a posting, a typo in a number in `.env` no longer stops the app, two saves at the same moment cannot collide, and the email command keeps what it read when Claude's limit runs out.

## 9 October 2026

- **An illustrated guide** (`docs/GUIDE.md`): every screen with a picture, what it is for, why it is needed and how to use it, in 17 sections. The pictures show invented people and companies and can be taken again with one command.
- **Help and README brought up to date** with moving documents and putting them back, the Trash, picking your profession, reading a posting again and closed postings.
- **Keywords for other professions**: "Keywords in the posting" now also knows the telling terms of finance, sales and marketing, HR, law, engineering, logistics, health care, hospitality, teaching, design, laboratory work and construction (235 terms instead of 112).
- **More professions to pick from**: design and media, science and laboratory, construction and trades, office and public administration, retail, security and facilities were added (17 in all), and the earlier ones know more titles, some in Czech.
- **No text is cut off any more**: long job titles, company lines, status messages and labels now wrap, and their row grows, instead of ending in "…".
- **Errors the app carries on after are written down**: `data/app_trouble.log` gets one line when, for example, the saved Options cannot be read or a folder does not open. Addresses lose their query part, so no key ends up there.
- **Resume button**: a darker blue, so its white label reads.
- **Postings that closed are noticed**: each search asks the pages of earlier LinkedIn postings (at most 40 per search, each at most every 3 days) whether they still accept applications. A closed one without documents moves to the filtered-out list; one with a letter or CV stays and is marked "no longer accepts applications".
- **Fixed: documents moved while a search was running** came back as broken links when the search finished. The move (and putting back) now reaches the running search too.
- **A handbook** (`HANDBOOK.md`): how to use the app, the rules it is built by, how the code is laid out, how a change is checked, and what is left to do.
- **Dark theme is easier to read too**: the label on the orange buttons, picked chips and the green tick is now dark in the dark theme (white on light orange was hard to read), and hint text is a little brighter.
- **Old moved documents go to the Trash**: "Remove" in Options no longer deletes them; it moves them to the Trash of their disk, and does nothing if that disk has no Trash.
- **Fixed: "scored from a short summary" on applications**: the tag is only shown on a new job that has a score.
- **Light theme is easier to read**: hints, warnings, the green and red notes and the orange of the main buttons are darker in the light theme, so small text no longer fades into the background.
- **Pick your profession yourself**: under "Kinds of role you want" in Options, choose the professions the free first look should treat as yours, or leave it to the app.
- **Each job that could not be moved or put back is listed** in New Jobs with its own reason, instead of one long line.
- **Old moved documents can be removed**: Options shows how many letters and CVs are in the backup after "Move to backup" and removes those older than the age you set, after asking with the count. Copies younger than 7 days are always kept.
- **Fixed: moved documents were at risk from the automatic clean-up**: the "Keep backups" limit would have treated their folder as one old backup. It is now left alone.
- **The free first look follows your profession**: which titles count as "another profession" now comes from the roles you look for (or your CV), not from a list written for software jobs. Options shows what the app takes as your profession. A title naming a role you listed as not wanted is skipped before scoring, and a language your CV shows is no longer a reason to skip.
- **A second read for every board**: a posting from any other board or company page that came back empty or short is read from the copy the page itself publishes. A site that turns programs away (Jooble) is not asked again; paste its text instead.
- **Put moved documents back**: for a week New Jobs offers "Put them back" for the last batch moved to the backup, and a job's own window offers it for that job at any time. Nothing is put back if a file is in the way or a backup copy is missing.
- **Scored at once on the new text**: after "Read it again" or pasting a posting's text, the job is scored again by itself (one Claude call). If a search is running or Claude cannot be asked, the window says so and keeps the text.
- **Move all documents below your limit at once**: New Jobs shows how many jobs still have a letter and CV from a higher score, and one button moves them to the backup after naming the jobs and asking.
- **Full text for company-branded job pages**: postings on pages like `company.jobs.cz` used to give only a short summary; the app now reads the whole posting, in a search and with "Read it again".
- **The earlier score in the list**: a job that was scored again shows "was 55" under its score in New Jobs.
- **A second try at reading a posting**: when a job board returns no text, the app tries once more before scoring, and the job window has "Read it again".
- **Scores say what they rest on**: a job scored from its title only, or from a short summary, is marked in the list and in its window. A title alone scores 40 at most and gets no letter.
- **Paste the posting's text**: when the app could not read a posting, you can paste its text in the job window and score it again.
- **Documents from a higher score are marked**: a job that now scores below your limit but still has a letter and CV says so, and "Move documents to backup" puts them away.
- **Options asks before discarding changes** when you close it with ✕ or Esc.
- **Score again**: a new job can be scored again from its window with your current Options (one Claude call), and the New Jobs list has "Score all again". Only scores change; the old score stays visible.
- **The older windows explain wrong input too**: the letter editor (empty paragraphs, closing with unsaved changes), the career-site name, and number fields, which now say what they accept instead of ignoring a wrong number.
- **Every text field says when it is full or too long**: company notes, a date's note, a pasted reply, form answers, the preparation lists and the About you fields now show the limit in red, and nothing you typed is cut silently when saved.
- **Edit the preparation in the app**: every part of the interview sheet can be changed and saved; "Make again" asks before replacing your changes.

## 8 October 2026

- **A required language is checked by the app itself**: when a posting requires a language your CV does not show (for example "Czech or Slovak"), the score is lowered to 25 and the reason says so, whatever the model scored.
- **Kinds of role you want and do not want** (Options): the score now measures fit for your direction. A role in another field scores 40 at most; a kind you do not want, 20 at most.
- **Questions to ask that fit you**: the interview sheet no longer suggests asking about visa or relocation when your right to work is known, or questions that point at your own weak spot.
- **What you can ask them**: the interview sheet lists questions for you to ask, separately for HR and for the engineer, under each set.
- **Two sets of interview questions**: what HR or a recruiter asks, answered in plain words without jargon, and what an engineer asks, answered precisely.
- **Each job told two ways**: the full story and a plain-words version for HR, plus what people in that kind of position usually do, marked as general knowledge about the role.
- **Your work experience, told for the role**: the interview sheet now has a section per job from your CV: how to tell it for this role, what it gave you, and questions that help you recall real details.
- **More about your work** (Options → About you): describe what you really did in each job beyond the CV. Interview preparation and form answers use it like your CV.
- **Interview preparation as a document**: preparing an interview now gives a sheet to read before the call: the company, the role, your fit, the honest gap, the key question, an opening pitch, likely questions with answers, concepts to explain, questions to ask and reminders. "Open as document" writes it as a Word file.
- **Show in folder**: the CV, the letter and the single PDF can be shown in Finder with the file selected, ready to drag into an application form.
- **Readable descriptions**: a posting's text is laid out with headings on their own lines and list items marked. No word is changed.
- **Notifications with the app's own icon and name**, and clearer wording ("40 new jobs found. 20 are ready to send, with a CV and letter.").
- **App icon** in the Dock and the window.
- **Postings on company-branded jobs.cz pages are read properly**: those pages load their text by script, so the app got no company and no text, could not see that an ad was in Czech, and scored it from the title. It now reads the company and a summary from the page.
- **The same posting is no longer listed twice**: ids made from a link changed on every run; the same link now counts as one posting.
- **Scan result names invitations**: the line after an email scan says "3 new: 2 invitations, 1 rejection" instead of counting only rejections.
- **Interview date saved from the email**: when a reply fixes a day and time, it becomes the job's date to remember (shown under Coming up), unless you already set your own.
- **Right application at a company with several**: an email that names no role goes to the open application that is furthest along, and the company's own name ("Robotics") is no longer read as a role word.
- **No letter without a company name**: a posting that gives no company gets a score but no letter or CV, and the job window says why. The name is taken from the posting text when it is there.
- **API keys never appear in error messages** or log files.
- **A command-line or weekly search updates the Last run card** too.
- **Your own letter stays with its application**: a new job at a company you once wrote to no longer gets that old letter; the app writes a fresh one for the new role.
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
