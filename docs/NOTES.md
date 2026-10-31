# Engineering notes and known limits

Why JobHelper is built the way it is, and what it cannot do yet. For how to install and run it, see the
[README](../README.md); for the code itself, the [technical documentation](CODE.md).

## Engineering notes

A few decisions worth highlighting, each with the problem that led to it.

- **The model is asked only what code cannot decide.** Language, level, location, duplicates
  and "another profession" are settled in plain code before scoring, so a search of several
  hundred postings costs a few dozen calls. Lists that decide what is skipped were measured on
  real postings before they shipped: nothing that had scored 30 or more may be skipped.
- **What the model writes is checked after it wrote it.** A prompt that says "do not invent"
  is not a guarantee. A whole run with an invented accountant's CV showed an adapted CV stating
  the posting's terms ("cost center data") as experience; the check that came out of it finds a
  two-word term of the posting that the CV knows nothing of, sends the draft back once, and
  shows what remains to the person instead of cutting sentences out.
- **Claude proposes, the app disposes.** A free request to the assistant is one call that
  returns an answer or up to three actions from a fixed list. The app checks them (a made-up
  action or job is dropped), words the question itself, and changes nothing until the person
  says yes. Tests with forged replies confirm that none of them changes data.
- **A prompt is tried against the real model, not only against stand-ins.** A trial on invented
  data showed Claude reading the day a reply arrived as the day of an interview. The fix was
  not another instruction but the data itself: the line now says "an invitation arrived" and
  "no date set", which cannot be misread.
- **A page is filled in by small scripts that are tested on a real page.** One lists the
  fields without sending back what they hold; plain code decides what each field is; another
  writes values that travel as data, never as code, and only into the page that was read. The
  one script that presses anything accepts five kinds of element and reads their words again
  before it acts. The test area found what unit tests had missed: "Czechia" in a list that says
  "Czech Republic", a job's employer paired with another job's title, a page that throws away
  whatever did not arrive as typing.
- **A background thread still blocks the window in Python.** Preparing the Insights view was
  59,000 small text searches; although it ran in a worker, the welcome animation stuttered for
  half a second because every call from the window queued behind it. The work now starts after
  the welcome screen and rests briefly after each posting (733 ms of stalls before, 30 ms now).
- **A running search holds its own copy of the job list.** A hand edit made meanwhile must
  reach that copy too, or the search writes its older copy over it when it ends. One function
  applies every edit to both, which is why an edit must give the same result when run twice.
- **The limit is a state, not an error.** The numbers the usage card shows are a snapshot from
  Claude's last answer; a refusal fills the limit it names until its reset time, and a run
  pauses and resumes instead of failing job after job. Claude reports the numbers only with an
  answer, so a number older than an hour shows "as of" and its time.
- **Replies are matched by a company's own name words.** "Accenture Czech Republic" and "PwC
  Czech Republic" share a word, and so do "Reed Specialist Recruitment" and an "IT Support
  Specialist" role elsewhere. Words many names share do not count; measured on 150 days of real
  mail, that moved eight replies to the right company and lost none.
- **The documentation is built and tested like code.** The user guide's pictures are taken by
  a script from invented data, figures and tables are numbered by a tool, and the PDF builder
  lays pages out itself: a figure or a table is never split, the text that follows it fills the
  space it left, and every entry of the contents can be clicked.

## Known limits

**The app as a whole**

- macOS only.
- The built app is signed only for the Mac that built it, not by Apple. On another Mac it opens
  after **Open Anyway** in System Settings → Privacy & Security.
- It needs a Claude subscription and the Claude Code CLI. When the 5-hour or the weekly limit
  of the subscription is used up, writing, scoring and the assistant's answers wait for the
  reset; a running search pauses and goes on by itself.
- The size of text and controls (100% to 150%) is read when the app starts, so a change needs
  a restart.

**Finding and scoring jobs**

- The job boards with full support are Czech (jobs.cz, prace.cz); other countries rely on
  LinkedIn, company career sites and the remote boards.
- A board that changes its pages can stop giving results until its reader is updated.
- The built-in salary estimate covers software roles in Czechia; elsewhere you enter your own
  figure.
- Russian services are not used: no such mail provider, job board or site.

**Email**

- Outlook.com, Proton and Tuta mailboxes cannot be read with a password, so they cannot be
  connected.
- The mailbox is only read. The app never sends, deletes or marks a message, so replies are
  written by you.

**Documents**

- CVs and letters are written from a Word (`.docx`) master CV and letter template. A CV with an
  unusual layout may lose less-common sections from the adaptation; the app then leaves them as
  they were.
- PDFs are made with LibreOffice; without it only the Word files are written.
- A letter or CV is checked against the master CV and your notes, so a posting far from your
  experience gives a short, plain letter. The checks are plain code and do not catch everything: a
  duration ("over the past year"), a claim that names no job ("used Docker daily") and an employer
  the model invented are not caught. Read each letter before you send it.

**The assistant**

- It works in Chrome, Brave, Edge, Opera and Safari, after the browser's switch **Allow
  JavaScript from Apple Events** is turned on and macOS is allowed to control the browser.
  Opera GX and Firefox do not let another app fill their pages.
- It has been tried on a few real recruiting sites. Lists in particular are drawn in many ways,
  and a new site may need a fix.
- It cannot reach a form inside a frame from another site (it offers to open the frame in its
  own tab), or an uploader that has no file field until its button is pressed (it then shows
  the files in Finder).
- It attaches the CV and the letter of the job only when it knows which job the form is for,
  and only files up to 4 MB. Certificates, a photo or a passport are yours to add.
- It never presses Submit or Next, never answers a field that agrees to something, and never fills
  in a password, a payment field or a personal-status question.
- An answer comes back whole, not word by word, because the app checks it before showing it.
