# What changed

The newest changes are first. The Help window in the app shows this file under "What changed".
Format: a `## ` heading, then one `- ` line per change; `**words**` are shown in bold. Changes not yet
in a version go under `## Unreleased`; a released version's heading is `## 1.1.0 – 18 October 2026`
(its tag is `v1.1.0` on GitHub). Version 1.0.0 is everything up to 17 October 2026, listed by date.

## Unreleased

- **Notifications now reach you.** macOS had kept every JobHelper notification without showing it. The app now shows them itself, so macOS asks once and lists JobHelper in System Settings → Notifications. **Options → Notifications** has a **Test** button and says in red when macOS has them turned off.
- In the **country picker for remote jobs**, the **job table** and the **filing list for a reply**, a click on the list now ends typing in the search box. Before, its outline and cursor stayed.
- The licence file is now **LICENSE.md**, so GitHub shows its headings and links instead of raw text. The text of the licence did not change.
- New **Remote jobs** choice in Options. A remote job tied to one country ("USA Only", "Remote, South Korea") is kept only for your country and the countries you add in a window that finds them by name or by part of the world. A job for a part of the world ("Remote – APAC") is kept when your country is in it, or always with **Anywhere in the world**. It applies to remote jobs from every source. Before, a remote job tied to a country the app did not know, such as "Remote, South Korea", was kept as if it were open to anyone; the app now knows every country.
- A job posted on **two boards is no longer lost** when the copy the search kept was then filtered out, for example as written in Czech or as too old. The duplicate check now comes after the other filters, so a copy is left out as a duplicate only when another copy is kept.

## 17 October 2026

- **Job sources in any combination**: Options now has a chip for each kind (Czech boards, LinkedIn, Career sites, Remote boards); select one or more. The main screen shows the names of the sources a search reads instead of "+ Remote". Before, "LinkedIn only" and "Company career sites only" also read the remote boards when "Include remote jobs" was on.

## 16 October 2026

- The widget is **brought up to date as soon as the app starts** and whenever your numbers or dates change; before, it showed the new numbers only at its next own check, up to 15 minutes later.
- A date with a time **leaves "Coming up" one hour after it starts**, in the window, the widget and the reminders. Before, an interview at 13:30 still showed as coming up in the evening.
- The widget's last run shows the **same number of new jobs as the window** (it showed 0), and the weekly run reads "Weekly run off" instead of just "Off".
- The widget now **shows your numbers**: it had looked for them in its own sandbox folder and said "Open JobHelper once" while the app was open.
- The widget has a fourth size, **extra large**, with all the numbers, the next five dates and the Claude usage side by side.
- The widget now **appears in Edit Widgets**, looks like the macOS widgets, and has an **Open** button that opens the app.
- New **JobHelper widget** for the desktop and the Notification Center, in three sizes: new jobs, applications, interviews, follow-ups, the next dates, the last run and the Claude usage left. Add it with Edit Widgets.
- A search for a **city outside Czechia** no longer reads jobs.cz and prace.cz, even when Job source is still set to the Czech boards. The log of the run says so.
- Each question the app sends to Claude is about **1.5 seconds faster**: your claude.ai connectors are no longer started for it.
- The Mac app no longer makes macOS ask for your **Desktop, Downloads, music, removable disks or other apps' data**. The Claude program it starts had looked at the whole disk; it now works in an empty folder of the app's own.
- JobHelper is now a **Mac app**, JobHelper.app: it opens from Applications like any other app, with no Python or terminal. The user guide shows how to open it the first time.
- The welcome card now names what is still needed, for example **your master CV**, instead of always saying two things.
- The Account card has a fifth row, **PDF copies**. It says whether LibreOffice is on your Mac, and how to get PDF copies when it is not.
- A notification that the app's notifier cannot show now appears **the plain way**, and an old message that waited too long is not shown late.
- The Claude sign-in is checked, and started, with **the same Claude program that answers the app's questions**, so the Account card is right also when the app is opened from Finder.
- The **weekly run** now starts the app itself, with no window, so it also works for an app that is not run from its project folder. When you open the app, it points an older weekly run at itself, on the same day and time.
- Your data now lives in **your Library** (Application Support, folder JobHelper), the usual place for a Mac app, so a new version of the app never touches it. At the first start the app moves it there once, checks every file, and keeps the old folder as data_moved_to_Library.
- The red line of the start-up check now has a button that fixes the problem: **Repair** gives jobs with an unknown status a status the app knows, and **Restore from backup** puts back the newest copy of a damaged job list or replies database. The line becomes green when the fix is done.
- Messages about the data key, backups and the search city no longer tell you to type a command. They tell you **what to do in the window**.

## 15 October 2026

- **Interview preparation** now opens as two Word documents: one for a talk with HR, one for a talk with a specialist. Both go in this order: the company, you, your projects and skills, the questions they may ask you, and the questions you can ask them.
- The preparation has a new part, **your projects and skills**, each with where your CV shows it. Select **Make again** on an older preparation to get it.
- In the technical document, each project explains its tools and methods: **what each one is, what it did in the project, and the technical reason it suits that task**. It also gives the result and the questions a specialist may ask. Each skill gets more detail.
- The **preparation window** shows your projects and skills too, before the questions.
- The questions you can ask HR always include the **next steps**, and ask about the team, working hours, the first weeks and the contract.
- The **user guide** and the **code documentation** now follow ASD-STE100: no sentence over 20 words in a step or 25 words in a description, one idea in each sentence, and lists where a sentence named many things. A test keeps them that way.
- The preparation is written in **ASD-STE100 Simplified Technical English**: short sentences, the active voice and common words.
- **Inside the app:** the back end of the window is now a facade over ten small services, each with one job (object-oriented rules). Nothing changes in how the app looks or works.
- **Inside the app:** each job board is now a source object with the same interface (find, forget, available), so a new board can be added without changing the search.
- **Inside the app:** a mailbox is now read through one `Mailbox` object that can only read and always signs out, also after an error.
- **Inside the app:** the tests no longer read your own CV or letter template (they use test files), and a test run now fails if anything in your own `data` folder changes while it runs.
- **Inside the app:** letters and CVs are now changed through one `WordDocument` object that keeps every part of the file except its text exactly as it was. The files the app writes are the same, byte for byte.
- **Inside the app:** My details is now checked by small classes (one per list: jobs, degrees, languages; the salary; the files). The checks and their messages are the same.
- **Inside the app:** the interview preparation is now made of small classes (a question, a job, a project, a tool, a skill). Editing a preparation by hand now checks the tools of each project against your CV too, as making one does.
- **Inside the app:** the assistant's form logic is now made of small classes (a field, the rows of jobs and languages, the plan for a page). Nothing changes in how it fills a form.

## 14 October 2026

- When a company moves an interview, the new day and time from its invitation now replace the old **date to remember**. Before, a date an earlier email had set was kept, and the new one had to be typed by hand. A date you set yourself is still never changed by an email.
- A later email that names only the day of an interview (a reminder) keeps the time already saved.

## 11 October 2026

- **Found by reading the code line by line (fourth part: the smaller modules and the window's files):**
  - In the job window, what you typed and did not save yet is no longer wiped when another part is saved. Before, saving the company notes (or a finished scoring, or a ticked step) emptied a date you were still writing.
  - **Options** says so when you typed a role, a word or a company into a box and pressed **Save** without adding it. Before, it was left out without a word.
  - A job that could not be restored or merged now says why in the status line.
  - **Analytics** has a row for offer emails, so the rows under **Reply emails** add up again.
  - In the assistant's **My answers**, **Remove** asks once before it deletes an answer you keep. Before, one press removed it for good.
  - The assistant names the browser you chose in what it says, not always Chrome.
  - A number box (years, days, scores in **Options**) shows the right number again after you typed one and then pressed + or -. Before, the value changed but the box kept showing what you had typed.
  - A reply with a long summary no longer pushes its window past the edge of the app: the text scrolls, and the buttons and the **File under** list stay in view.
  - **Mark applied** no longer says "Moved to Applications" when the job was not moved (it was already an application, or it was gone from the list); it says so instead.
  - Titles and messages in the window use the short dash everywhere, as the documents do ("New Jobs – 12").
  - In a small window the **Account** card no longer runs past the bottom edge when the mailbox editor or the list of changed lines is open: its content scrolls, and **Done** stays in view.
  - **Help** has a topic about the **assistant**: what it fills in, which browsers it works in, and what it never does.
  - In **Options**, a suggested search role can be chosen with the arrow keys and Return, and a long suggestion takes a second line.
  - The usage card never shows less than 0% left.
  - The counters under **Usage and problems** survive a damaged file and two questions answered at the same moment.
  - A reply filed by hand while an email scan is saving is no longer lost.
  - Merging two entries of the same job keeps the date to remember, the interview preparation, the form answers and a status you set by hand.
  - The salary estimate matches whole words, so "ai" is no longer found in "Thai" or "ios" in "kiosk".
  - **One PDF** works when your own letter is already a PDF.
  - A message about a missing data key says where to paste the recovery key in the **Account** card.

## 10 October 2026

- **Found by reading the code line by line (third part: the assistant, the window's back end, the bridges):**
  - A right-to-work question that names another country than yours is never answered for you. What you said about your right to work is about your own country.
  - Stop pressed while a run waits on Claude's limit now ends the run at once. Before, the run went on to the next job, and the job it was on lost one of its two tries at documents.
  - **Mark applied** works for a new job only: a stray press no longer sets an answered application back to waiting.
  - **My details** is no longer read as empty when one saved value fails a check; only that value is left out.
  - The review before sending names a long list by the words beside it, not by the page's inner name.
  - The back end now refuses a career-site token that is not a plain slug, and a model or search source it does not know, whatever sent them.
- **Fixed on a real form: "Location" and "Role description" inside a job were filled wrongly.** The location got your own city and the description got a text Claude drafted about you in general. Each job in **My details** now has **Where it was** and **What you did there**; **Read from my CV** copies both from the CV, word for word. Forms get the job's own, and what is empty is left to you with the reason.
- **Dates split into a month box and a year box are filled in.** The From and To of a job were left empty on forms that draw them this way.
- **Languages.** **My details** has a list of your languages with a level each (Native, Fluent, Advanced, Intermediate, Basic). A form that asks for each language gets them row by row, with the level in the form's own words; where a form has no entry for Native, Fluent is chosen. The box "I am fluent in this language" is ticked for Native and Fluent.
- **A field's visible label now decides before its inner name.** A box labelled "Location" whose inner name contained "school" was taken for the school.
- **Found by reading the code line by line (second part: search, scoring, replies, documents):**
  - LinkedIn postings are now really asked whether they are still open. Postings from boards that cannot be asked used to fill the queue on every search, so most LinkedIn ones never were.
  - One job board that changed its pages no longer ends a whole search; the other sources go on, and the trouble log says which board failed.
  - A status you set by hand is no longer set back by an older email on every scan. An email newer than your change still counts.
  - Text from an email or a posting that begins with "=" is written into the Excel tables as text, never as a formula.
  - A reply Claude answered in an unexpected shape is still filed, and one email with an undecodable subject no longer ends a scan.
  - "Claude's limit is used up" is now said when you ask for one job's documents, instead of "Nothing could be written this time".
  - A LinkedIn posting's date is read from its own date line only; before, words elsewhere on the page could make an old posting look new.
  - For someone searching in India, Canada or a country the app has no table for, local postings written "City, IN" are no longer taken for the United States.
  - The Replies report lists applications in the order of their dates.
- **Found by reading the code line by line (first part):**
  - A CV that keeps its jobs or skills in a table is now read whole; before, only its paragraphs were, so true experience could look like something the CV does not say.
  - A Keychain that is locked or does not answer is no longer taken for an empty one, and no new data key is ever made for data that is already encrypted.
  - An email scan can no longer wait for ever on a mail server that stopped answering (one minute per answer at most).
  - On the command line, `apply` works only for a new job, a reached Claude limit keeps what was read, and a mailbox that refuses or cannot be reached is one sentence, not a traceback.
- **A form inside a frame: one press.** The button now reads **Open the form in its own tab and fill it in**, and does both. The message no longer prints the long address.
- **A phone number beside a list of country codes.** The assistant chooses the code of your number in the list and writes the number without it. When the list already shows another country, it leaves the list alone, writes the whole number and marks both for checking.
- **File fields the page hides behind its own buttons** are reported once, with what to do, not as several fields called "afile".
- **Size of text and controls.** Options has a new setting that draws everything in the window larger (110%, 125% or 150%), for a large or very sharp screen. It is used the next time you open the app.
- **The assistant fills in when you can start.** "Earliest start date", "Available from" and "When can you start?" get what you entered under Options, About you. A date picker gets the day itself: a date as written, *immediately* as today, *one month* as a month from today, marked for checking when it was worked out.
- **Fewer half-empty pages in the PDFs.** When a figure or a table has to start on the next page and its own section has no more text, the next section of the same chapter now begins in the space. A figure never leaves its chapter and never goes further than the section after its own.
- **The README lists the known limits by area.**
- **Find a job for the assistant by typing.** Next to **Answers are for** there is a box: type part of a company or a title and the list narrows; when one job is left it is chosen and its full name shown. A name none of your jobs has is said in red.
- **The README names its author.**
- **Fixed on a real application form: "Field 5 - I did not recognise this field".** Some pages put an unseen box of their own under each list, to check that something was chosen. Those were listed as fields nobody could name. They are no longer counted.
- **Fixed: "The menu did not open for me" while the browser was behind the app.** Many lists open only when the page hears that their box was entered, and a window that is not in front is never told. The assistant now says so to the page itself, tries the arrow-down key when a press opens nothing, and asks for all entries when the list does not know your country under the name you gave. A list that already shows its answer beside its box is left alone.
- **A letter's head carries your own title.** The line under your name used to be the role applied for, so every letter called you something else. It is now the line under your name in your CV, the same one your CV and your profiles on the web show. Only a CV without such a line still gets the role. A letter you edit and save in the app is corrected the same way.
- **The assistant attaches your CV and your letter.** A form's field for the CV gets the CV adapted to the job (your own CV when there is none, and it says so); a field for the cover letter, or for other attachments when the form has no place for the letter, gets the letter of the job. A photo, a passport or any file it cannot place is left to you, as is a file over 4 MB or of a kind the field does not take. Nothing is attached when the job is not known.
- **The job of a form is found even when Apply leads to another address.** The assistant now also looks at the page that led to the form, at the company and the job title in the words of the page, and at the posting you last opened from the app.
- **Fixed: a long country list was left empty.** On a first real form the list of some 250 countries was not filled in. Its label is only written beside it, and the list's own entries crowded the label out, so the assistant could not tell what the list asked. A list is now named by the words beside it without its own entries, or by its first line ("Select your Country") when there are no words at all. A greyed-out "Please choose" line is no longer taken for an answer.
- **Opera GX cannot be used by the assistant, and the app now says so.** A first try showed that Opera GX has switched off the part that lets another app fill in a page; it is listed as not possible, like Firefox, with the advice to use Google Chrome or Safari. The refusal used to read "bring the tab to the front", which was wrong. Opera itself stays in the list. The button reads **Fill in the form**, and the line under the box says which browser is used.
- **Fixed: a list kept its outline after you clicked somewhere else,** like text fields did before. A press on empty space now lets go of it.
- **The assembly line grows with the window.** On a large screen the robots and their words used to stay small; the line now fills the room it has, and the words at the robots are larger. What the assistant says appears in a strip of its own under the line, so it never covers the line or a robot.
- **Judging a posting costs one Claude call, not three.** The button reads the job's title and employer from what the page states for search engines, so only the scoring asks Claude.
- **The PDF guides have no half-empty pages where text could stand.** When a figure or a table has to start on the next page, the text that follows it in the same section is brought forward. The entries of the contents, every "Figure 4.2" and "Table 9.1", and links to another chapter can be clicked, and the chapters are in the PDF's outline. List points have a heavy mark and steps a bold number.
- **The technical documentation explains its processes with diagrams:** a search, the honesty checks, an email scan, the limit, data protection, filling in a form, a request to the assistant, the layers of the code and the making of the PDFs.
- **The assistant does several things in one request, and you can undo them.** "Mark it applied and remind me to follow up in ten days" is asked about in one question that lists both steps. After your yes, **Undo** puts the job back exactly as it was.
- **The assistant remembers what you tell it.** "Remember that I do not want consulting firms" is kept for later talks, and a talk goes on where it stopped after the app was closed. The notes are on the My details page and can be removed there.
- **Is this posting worth applying to?** With a job posting open in your browser, the assistant reads it, scores it against your CV with the same scorer a search uses, and adds it to New Jobs on your yes.
- **A reply to a company, drafted for you.** "Answer Quillon that Tuesday suits me" gives a short reply to their last message with a Copy button. The app still never sends mail.
- **Safari, Brave and Edge.** Choose the browser on the My details page under **How I work**; the switch to notice forms moved there too.
- **More of a form is filled in:** a date asked as a month list and a year list, the box **I currently work here** for a job you marked as current, and fields on pages that throw away what was written the first time.
- **Practice keeps score.** The questions that went badly last time come first, and the practice ends with how many answers were good, fair or weak. What you typed is not kept.
- **The assistant says what it is doing** while you wait, writes its answer out as it appears, and sends Claude only the jobs a request is likely about instead of the whole list.
- **Fixed: the assistant could read the day a reply arrived as the day of an interview**, and could guess why a job scored as it did. Found by trying the prompts against the real Claude on invented data.
- **You can talk to the assistant in your own words.** Ask about your search ("which applications have had no reply for two weeks?"), about a job ("why did this score 62?"), or ask it to do something ("mark it applied", "set the interview for Tuesday at 11:30", "open the letter"). It remembers the last turns of the talk, and "this job" means the job whose window is open. Before anything of yours changes it asks, and waits for **Yes, do it**. Filling in a form and help still cost nothing; anything else is one Claude call.
- **Rewrites by instruction.** "Make the second paragraph of this letter shorter" or "make my salary answer more formal": the assistant shows the new version, checked against your CV, and saves it only after your yes.
- **Review before I send.** After a fill, the assistant reads the form back and lists what looks wrong: a required field left empty, a part still in square brackets, an email that is not yours, an answer that contradicts your CV or names another company.
- **Interview practice.** Ask the assistant to practise for an application: it asks the questions of the interview preparation one by one and says what is good and what is missing in each answer you type.
- **Company brief and advice.** "Tell me about Northwind before the interview" gives a few lines from the posting, your notes and their messages; "what do my results say?" reads the numbers of your own applications.
- **The assistant speaks first.** When the app opens, its bubble says what needs your attention: a form you filled in but did not mark applied, an interview in the next two days with no preparation, an invitation with no date. Its window lists the same under **For you today**. This uses no Claude call.
- **Noticing a form by itself (off until you turn it on).** With the new switch on the Ask page, the assistant looks at the address of the tab in front in Chrome every 20 seconds and tells you when it is the form of a job you track.
- **More of a long form is filled in.** The dates of a job go into its row; a short field the app does not recognise is filled with words copied from your CV, or left; and where a form has a button such as **Add another job**, the assistant presses it once for each job or degree that has no row yet. It presses no other button.
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
