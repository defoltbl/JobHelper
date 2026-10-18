"""Shared email access + job-matching helpers (used by Agents 4 and 5).

READ ONLY: connects to your inbox over IMAP with BODY.PEEK, so nothing is ever
marked read, sent, or deleted. For Gmail, use an App Password (not your real
password).
"""
from __future__ import annotations

import email
import imaplib
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.header import decode_header
from typing import Any, Callable

from . import config, store

# Map an extracted stage → an application status. Never move a job backwards
# (except "rejected", which can apply from any stage).
STAGE_TO_STATUS = {
    "acknowledged": "waiting",   # they confirmed receipt — still awaiting a decision
    "assessment": "interview",
    "interview": "interview",
    "offer": "offer",
    "rejection": "rejected",
}
RANK = {s: i for i, s in enumerate(store.STATUSES)}


def status_after(current: str, stage: str) -> str:
    """The status a reply of this stage moves an application to, or '' when it leaves it as it is.
    Forward only ("interview" never goes back to "waiting"); a rejection applies from any status."""
    new = STAGE_TO_STATUS.get(stage, "")
    return new if new and (new == "rejected" or RANK.get(new, 0) > RANK.get(current, 0)) else ""


def _decode(value: str | None) -> str:
    if not value:
        return ""
    out = []
    try:
        pieces = decode_header(value)
    except Exception:  # noqa: BLE001 - a header nobody can decode is read as it stands
        return str(value)
    for text, enc in pieces:
        if not isinstance(text, bytes):
            out.append(text)
            continue
        try:
            out.append(text.decode(enc or "utf-8", errors="ignore"))
        except LookupError:                  # "unknown-8bit" and other names of no encoding: one such subject ended a whole scan
            out.append(text.decode("utf-8", errors="ignore"))
    return "".join(out)


def _part_text(part: email.message.Message) -> str:
    payload = part.get_payload(decode=True)
    if not payload:
        return ""
    try:
        return payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
    except LookupError:                      # unknown charset name in the header
        return payload.decode("utf-8", errors="ignore")


def html_to_text(html: str) -> str:
    """Readable text of an HTML email (scripts, styles and hidden preheaders dropped)."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html or "", "lxml")
    for tag in soup(["script", "style", "head", "title", "meta"]):
        tag.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")
    text = soup.get_text(" ")
    lines = [re.sub(r"[ \t\u00a0\u200b\u200c\u200d\ufeff]+", " ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def _has_plain_text(msg: email.message.Message) -> bool:
    return any(part.get_content_type() == "text/plain" and _part_text(part).strip()
               for part in (msg.walk() if msg.is_multipart() else [msg]) if not part.is_multipart())


def _body_text(msg: email.message.Message) -> str:
    """The message as plain text. Many ATS mails (Workday, Gem, Greenhouse) are
    HTML only, so the HTML part is used when there is no usable plain part."""
    plain, html = "", ""
    for part in (msg.walk() if msg.is_multipart() else [msg]):
        if part.is_multipart() or part.get_content_disposition() == "attachment":
            continue
        kind = part.get_content_type()
        if kind == "text/plain" and not plain:
            plain = _part_text(part)
        elif kind == "text/html" and not html:
            html = _part_text(part)
    if plain.strip():
        return plain
    return html_to_text(html) if html.strip() else ""


# Wording that only a rejection uses. Deliberately narrow: it must never fire on
# a confirmation ("unfortunately we cannot reply to every applicant").
_REJECTION = [
    (r"position has (?:now )?been filled|role has (?:now )?been filled|(?:position|role|vacancy) is no longer (?:available|open)"
     r"|pozice (?:již )?byla obsazena", "position_filled"),
    (r"(?:moving|move|proceed(?:ing)?|going) forward with (?:other|another)\b[^.]{0,40}candidate"
     r"|decided to (?:pursue|proceed with|move forward with|go with|continue with) (?:other|another)"
     r"|(?:other|another) candidates? (?:whose|who|that)\b|selected (?:another|a different) candidate"
     r"|rozhodli (?:jsme se )?pro jiného (?:kandidáta|uchazeče)", "went_with_other_candidate"),
    (r"(?:will not|won't|are not|not) be (?:moving|proceeding|progressing|going) (?:forward|further|ahead)"
     r"|(?:not|unable) to (?:move|proceed|progress) (?:forward|further|ahead)? ?with your (?:application|candidacy)"
     r"|decided not to (?:move|proceed|progress|continue)|regret to inform you"
     r"|you (?:have|were) not (?:been )?(?:selected|shortlisted|successful)|your application (?:has not been|was not|will not be) "
     r"(?:successful|selected|shortlisted|progressed|considered further)"
     r"|unfortunately[^.]{0,80}(?:not (?:be )?(?:able to offer|offering|selected|progress|proceed|move)|unsuccessful)"
     r"|bohužel[^.]{0,80}(?:nevybrali|nepostoupil|nebyl[ai]? (?:jste )?vybrán)|litujeme[^.]{0,60}(?:nevybrali|nemůžeme)",
     "no_reason_given"),
]


# A sentence that only explains what *would* mean a rejection ("if you do not hear
# from us ...", "inactive means you were not selected") is not one.
_HYPOTHETICAL = re.compile(
    r"\b(?:if|in the event|in case|whether|either|should you|that means|this means|would mean|may mean|"
    r"serve as|does not mean|pokud|v případě)\b", re.IGNORECASE)


def rejection_wording(text: str) -> str:
    """A rejection category if the text clearly says the application was turned
    down, else ''. Used as a safety net next to the model's own reading."""
    flat = re.sub(r"\s+", " ", text or "")
    for pattern, category in _REJECTION:
        for m in re.finditer(pattern, flat, re.IGNORECASE):
            start = max(flat.rfind(". ", 0, m.start()), flat.rfind("! ", 0, m.start()), flat.rfind("? ", 0, m.start())) + 1
            end = flat.find(". ", m.end())
            sentence = flat[start:end if end != -1 else len(flat)]
            if not _HYPOTHETICAL.search(sentence):
                return category
    return ""


@dataclass(frozen=True)
class Fetched:
    """The messages one fetch read, and what it could not read (a folder, the second mailbox) as warnings:
    the fetch goes on without them, and the scan says so at its end."""
    messages: list[dict[str, Any]]
    warnings: tuple[str, ...] = ()


SERVER_TIMEOUT = 60.0       # seconds a mail server gets for one answer


class Mailbox:
    """One mailbox, opened read-only. Use it with `with`: it signs out at the end, also after an error.

    Read-only by design: `open()` always opens a folder read-only and `message()` always reads
    with PEEK, so nothing is marked, moved or changed. The class has no way to write.
    `connect` makes the connection to the server (tests pass a stand-in)."""

    def __init__(self, user: str, password: str, host: str = "", timeout: float = SERVER_TIMEOUT,
                 connect: Callable[[], Any] | None = None) -> None:
        self.user = user
        self._password, self._host, self._timeout = password, host, timeout
        self._connect = connect or (lambda: imaplib.IMAP4_SSL(self._host or config.imap_host(1), config.IMAP_PORT, timeout=self._timeout))
        self._imap: Any = None
        self.warnings: list[str] = []      # folders `recent` could not read

    def __enter__(self) -> "Mailbox":
        # a time limit on every step: a server that stops answering ends the scan with an error, not holds it for ever
        self._imap = self._connect()
        try:
            self._imap.login(self.user, self._password)
        except BaseException:
            self.close()
            raise
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        try:
            if self._imap is not None:
                self._imap.logout()
        except Exception:  # noqa: BLE001 - the connection is gone either way
            pass
        self._imap = None

    def folders(self) -> dict[str, str]:
        """The provider's "all mail" and "spam" folders, whatever they are called
        (their names depend on the account's language), found by their IMAP flags."""
        found: dict[str, str] = {}
        try:
            _typ, lines = self._imap.list()
        except Exception:  # noqa: BLE001
            return found
        for line in lines or []:
            raw = line.decode("ascii", "replace") if isinstance(line, bytes) else str(line)
            name = raw.split(' "/" ', 1)[-1].strip() if ' "/" ' in raw else ""
            if not name:
                continue
            if "\\All" in raw:
                found["archive"] = name
            elif "\\Junk" in raw or "\\Spam" in raw:
                found["spam"] = name
        return found

    def open(self, folder: str) -> None:
        """Open a folder, always read-only."""
        self._imap.select(folder, readonly=True)

    def since(self, since: str) -> list[bytes]:
        """The numbers of the messages in the open folder from that day on ("07-Sep-2026")."""
        _typ, data = self._imap.search(None, f'(SINCE "{since}")')
        return _numbers(data)

    def archive_only(self, since: str) -> list[bytes]:
        """Gmail: the archived messages from that day on that are in no other folder we read or wrote."""
        after = datetime.strptime(since, "%d-%b-%Y").strftime("%Y/%m/%d")
        _typ, data = self._imap.search(None, "X-GM-RAW", f'"-in:inbox -in:sent -in:drafts -in:chats after:{after}"')
        return _numbers(data)

    def message(self, num, folder: str) -> dict[str, Any] | None:
        """One message of the open folder, read without marking it."""
        _typ, msg_data = self._imap.fetch(num, "(BODY.PEEK[])")
        if not msg_data or not isinstance(msg_data[0], tuple):
            return None
        try:
            return _message(msg_data[0][1], num, self.user, folder)
        except Exception as e:  # noqa: BLE001 - one message that cannot be taken apart is left out; the others are still read
            from . import trouble
            trouble.note("reading one message of the mailbox", RuntimeError(type(e).__name__))
            return None

    def recent(self, since: str, all_folders: bool = False) -> list[dict[str, Any]]:
        """Recent messages: the Inbox, and with all_folders also archived mail and spam (not Sent or
        Drafts, and nothing you wrote yourself). A folder that cannot be opened is a warning."""
        out: list[dict[str, Any]] = []
        seen: set[str] = set()

        def take(folder: str, numbers, own_too: bool = False) -> None:
            for num in reversed(numbers):            # newest first
                item = self.message(num, folder)
                if item and item["msg_id"] not in seen and (own_too or self.user.lower() not in item["sender"].lower()):
                    seen.add(item["msg_id"])
                    out.append(item)

        self.open("INBOX")
        take("inbox", self.since(since), own_too=True)  # the Inbox keeps mail you sent to yourself too
        if all_folders:
            extra = self.folders()
            if extra.get("archive"):
                try:
                    self.open(extra["archive"])
                    try:
                        numbers = self.archive_only(since)
                    except imaplib.IMAP4.error:
                        numbers = self.since(since)
                    take("archive", numbers)
                except imaplib.IMAP4.error:
                    self.warnings.append(f"The archive folder of {self.user} could not be read.")
            if extra.get("spam"):
                try:
                    self.open(extra["spam"])
                    take("spam", self.since(since))
                except imaplib.IMAP4.error:
                    self.warnings.append(f"The spam folder of {self.user} could not be read.")
        return out


def _message(raw: bytes, num, user: str, folder: str) -> dict[str, Any]:
    msg = email.message_from_bytes(raw)
    return {
        "msg_id": _decode(msg.get("Message-ID")) or f"num-{user}-{folder}-{num.decode()}",
        "date": _decode(msg.get("Date")),
        "sender": _decode(msg.get("From")),
        "subject": _decode(msg.get("Subject")),
        "body": _body_text(msg),
        "was_html_only": not _has_plain_text(msg),
        "mailbox": user,
        "folder": folder,
    }


def _numbers(data) -> list[bytes]:
    """The message numbers of a search answer; a server that answers with nothing found nothing."""
    return data[0].split() if data and isinstance(data[0], (bytes, bytearray)) else []


def try_login(user: str, password: str, timeout: float = 8.0, host: str = "") -> dict[str, Any]:
    """Sign in to the mailbox and out again, to learn whether the address and password work.

    {ok: True} when they do; {ok: False, msg} when the server refused them; {ok: None, msg}
    when the server could not be reached, which says nothing about the password. Read-only:
    no folder is opened. The password is never part of a message."""
    try:
        imap = imaplib.IMAP4_SSL(host or config.imap_host(1), config.IMAP_PORT, timeout=timeout)
    except (OSError, imaplib.IMAP4.error):
        return {"ok": None, "msg": "The mail server could not be reached, so the password was not tried."}
    try:
        imap.login(user, password)
    except imaplib.IMAP4.error:
        return {"ok": False, "msg": "The mail server refused this address and password. Check both. Most providers want a "
                                    "separate app password for a program, not the one you sign in with."}
    except OSError:
        return {"ok": None, "msg": "The connection to the mail server was lost, so the password was not tried."}
    finally:
        try:
            imap.logout()
        except Exception:  # noqa: BLE001 - already closed
            pass
    return {"ok": True, "msg": ""}


def read_mailbox(user: str, password: str, since: str, all_folders: bool = False, host: str = "") -> Fetched:
    """Recent messages of one mailbox (see `Mailbox.recent`); it is signed out of at the end."""
    with Mailbox(user, password, host) as box:
        return Fetched(box.recent(since, all_folders), tuple(box.warnings))


def fetch_recent(lookback_days: int | None = None, all_folders: bool | None = None) -> Fetched:
    """Recent messages from the job mailbox, plus the optional second mailbox.

    A problem with the main mailbox is an error. A problem with the second one
    is only a warning: the scan goes on with the main mailbox."""
    boxes = config.mailboxes()
    if not boxes:
        raise RuntimeError(
            "No mailbox is connected. Add your job email in the app's Account card."
        )
    days = lookback_days if lookback_days is not None else config.IMAP_LOOKBACK_DAYS
    since = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
    if all_folders is None:
        all_folders = config.ui_settings().get("scan_all_folders") is True
    main = read_mailbox(boxes[0]["user"], boxes[0]["password"], since, all_folders, host=boxes[0].get("host", ""))
    out, warnings = list(main.messages), list(main.warnings)
    seen = {m["msg_id"] for m in out}
    for box in boxes[1:]:
        try:
            extra = read_mailbox(box["user"], box["password"], since, all_folders, host=box.get("host", ""))
        except imaplib.IMAP4.error:
            warnings.append(f"Couldn't sign in to {box['user']}: check its password in the Account card.")
            continue
        except OSError as e:
            warnings.append(f"Couldn't reach {box['user']}: {e}")
            continue
        out += [m for m in extra.messages if m["msg_id"] not in seen]     # the same mail delivered to both
        seen.update(m["msg_id"] for m in extra.messages)
        warnings += extra.warnings
    return Fetched(out, tuple(warnings))


# The legal form of a company and words around it ("Acme Corp", "Alfa spol. s r.o.", "Beta LLC"): never part of
# what tells two companies apart. One list for the key and for the name words: when they differed, "Alfa spol.
# s r.o." and "Beta spol. s r.o." shared the word "spol" and counted as one company, and so did two "… Corp"s.
LEGAL_WORDS = {"the", "group", "ltd", "limited", "inc", "incorporated", "corp", "corporation", "llc", "plc", "gmbh", "mbh",
               "sro", "spol", "sa", "se", "ag", "co", "bv", "nv", "oy", "srl", "spa", "sarl", "pte", "pty", "kft", "zrt"}


def company_tokens(company: str) -> set[str]:
    """The words of a company's name that can tell it apart from another (three letters or more, no legal form)."""
    tokens = re.findall(r"[a-z0-9]{3,}", (company or "").lower())
    return {t for t in tokens if t not in LEGAL_WORDS and t not in {"and", "czech", "com"}}


# Words many company names share. Two names that have only such words in common are two companies
# ("Good Data" and "NTT DATA", "Deutsche Bank" and "Deutsche Börse"), unless one is the other plus more.
GENERIC_COMPANY_WORDS = {
    "data", "systems", "system", "software", "solutions", "solution", "technologies", "technology", "tech", "services", "service",
    "bank", "banka", "consulting", "consultants", "international", "global", "digital", "labs", "lab", "holding", "holdings",
    "europe", "european", "prague", "praha", "czechia", "republic", "company", "partners", "capital", "energy", "health", "media",
    "network", "networks", "engineering", "industries", "research", "robotics", "analytics", "cloud", "security", "finance",
    "financial", "insurance", "pharma", "automotive", "logistics", "telecom", "mobile", "games", "studio", "studios", "design",
    "management", "central", "eastern", "deutsche", "ceska", "national", "united", "first", "new", "one", "career", "careers",
    "jobs", "recruitment", "staffing", "personnel", "innovation", "innovations", "development", "business", "enterprise",
    "enterprises", "trading", "investments", "ventures", "aktiengesellschaft",
    # words of job titles that also stand in company names ("Reed Specialist Recruitment", "NN Digital Hub"):
    # a reply about an "IT Support Specialist" role is not from that company
    "specialist", "specialists", "support", "hub", "academy", "talent", "people", "team", "experts", "professionals",
}


def same_company(a: str, b: str) -> bool:
    """Are these two names the same company? Equal once spacing, accents and legal forms are
    ignored; or they share a word that is really a name; or, when all they share is a common
    word, one name is the other with more added ("Data Systems" and "Data Systems Europe")."""
    na, nb = norm_company(a), norm_company(b)
    if na and na == nb:
        return True
    ta, tb = company_tokens(a), company_tokens(b)
    shared = ta & tb
    if not shared:
        return False
    return bool(shared - GENERIC_COMPANY_WORDS) or ta <= tb or tb <= ta


def norm_company(company: str) -> str:
    """A stable identity key for a company name, even when it has no usable
    tokens (e.g. "HP Inc." -> "hp", "NN Group" -> "nn"). Accents, brackets,
    spacing and the usual legal suffixes are ignored, so "Valeo" and
    "Valeo s.r.o.", or "CSOB" and "ČSOB (KBC)", collapse together."""
    text = unicodedata.normalize("NFKD", company or "").encode("ascii", "ignore").decode().lower()
    text = re.sub(r"\([^)]*\)", " ", text)            # "ČSOB (KBC)" is the same company as "CSOB"
    # dotted Czech legal forms would otherwise survive as loose letters
    text = re.sub(r"\bs\.\s*r\.\s*o\.?", " sro ", text)
    text = re.sub(r"(?<=\S)[\s,]+a\.\s*s\.?(?=[\s,]|$)", " ", text)   # trailing "a.s." only
    words = re.findall(r"[a-z0-9]+", text)
    kept = [w for w in words if w not in LEGAL_WORDS]
    return "".join(kept or words)


def job_of_company(company: str, jobs: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The first tracked job at this company (None when the name has no word to match by, or none is at it)."""
    if not company_tokens(company):
        return None
    return next((j for j in jobs if same_company(company, j.get("company", ""))), None)


def sender_domain(sender: str) -> str:
    """The domain of a From line ("Anna <anna@hr.acme.com>" -> "hr.acme.com"), lower case."""
    return re.sub(r"[^a-z0-9.]", "", (sender or "").lower().split("@")[-1].split(">")[0])


# Signals that an email is about a job application (EN + CZ), and ATS/recruiting
# sender domains. Used as a cheap pre-filter before spending an LLM call.
_APP_KEYWORDS = [
    "application", "position", "vacancy", "role", "interview", "candidate",
    "we regret", "unfortunately", "thank you for applying", "your cv", "your resume",
    "recruit", "hiring", "job offer", "assessment", "screening", "shortlist",
    "pozice", "přihláš", "životopis", "výběrové řízení", "litujeme", "děkujeme za",
    "pohovor", "nábor", "uchazeč",
]
_ATS_DOMAINS = [
    "greenhouse.io", "workable.com", "lever.co", "smartrecruiters.com", "recruitee.com",
    "teamio", "jobs.cz", "prace.cz", "jobs2web", "successfactors", "myworkday",
    "linkedin.com", "ashbyhq.com", "jobvite.com", "icims.com", "eu.jobs",
]


# Subjects/senders that look like alerts, digests, or confirmations — NOT replies
# to a specific application. Checked before the positive signals.
_NEGATIVE = [
    "new jobs", "jobs posted", "new job opportunit", "job opportunities at",
    "jobs for you", "recommended for you", "recommended jobs", "job alert",
    "job digest", "newsletter", "unsubscribe to stop", "account confirmation",
    "api key", "api account", "verify your email", "confirm your email",
    "cheat code", "weekly", "new matches", "jobs matching",
    "nových nabídek", "nabídek práce", "nabídky práce", "potvrďte svůj e-mail",        # job-board alerts and sign-up mail
    "one-time password", "verification code", "reset your password", "account created", "account creation",
]
_NEGATIVE_SENDERS = ["jobnotification", "jobs2web", "noreply@linkedin", "no-reply@linkedin",
                     "3scale", "newsletter", "digest@"]


# Marks of mail sent to a whole list, and of senders no person writes from.
_BULK = re.compile(r"unsubscribe|odhl[aá]sit|odhl[aá]šen|view (this email |it )?in (your |a )?browser|zobrazit v prohl[ií]že[cč]i"
                   r"|manage (your )?(email )?preferences|email preferences", re.IGNORECASE)
_AUTOMATED_SENDER = re.compile(r"(^|[<\s\"'])(no[-_.]?reply|do[-_.]?not[-_.]?reply|noreply|notifications?|notifikace|statements?"
                               r"|billing|invoices?|receipts?|marketing|news|promo|offers?|info|mailer)[^@\s]*@|@(notifikace|notifications?"
                               r"|news|newsletter|mail|email|e|em|marketing|info|promo)\.", re.IGNORECASE)


def names_tracked_company(sender: str, subject: str, jobs: list[dict[str, Any]]) -> bool:
    """Does the sender or the subject name a company you track, by a word that is really its name?

    A word many companies share ("international", "data", "praha") names nobody: an advert for an
    international conference is not from International SOS. A name made only of such words counts
    when all of it is there. A name too short to be a word ("HP") counts when it is the sender's domain."""
    words = set(re.findall(r"[a-z0-9]{3,}", f"{sender} {subject}".lower()))
    labels = set(sender_domain(sender).split(".")[:-1])
    for job in jobs:
        tokens = company_tokens(job.get("company", ""))
        own = tokens - GENERIC_COMPANY_WORDS
        if own & words or (tokens and not own and tokens <= words):
            return True
        short = norm_company(job.get("company", ""))
        if not tokens and len(short) >= 2 and short in labels:
            return True
    return False


def looks_like_application(sender: str, subject: str, body: str,
                          jobs: list[dict[str, Any]]) -> bool:
    """Cheap heuristic: is this email plausibly a reply to a specific application?

    Decides what is worth a question to Claude, so it must let every real reply
    through and keep advertising out:
    - obvious alerts, digests and sign-up mail are rejected first, even from a
      company you track ("New SAP Jobs Posted" is an alert, not a reply);
    - mail from a recruiting system passes;
    - mail whose sender or subject names a company you track passes when it
      talks about an application, and also without such words when a person
      wrote it (a recruiter's "are you free on Tuesday?"). Automatic mail from
      that company with no such words is a statement or an advert;
    - any other mail needs application words and must not be list mail.
    A company's name deep in the text is not enough: shops and newsletters
    mention brands and cities all the time.
    """
    low_sender = sender.lower()
    subj = subject.lower()
    if any(n in subj for n in _NEGATIVE) or any(n in low_sender for n in _NEGATIVE_SENDERS):
        return False
    if any(d in low_sender for d in _ATS_DOMAINS):
        return True
    hay = f"{subject} {(body or '')[:1500]}".lower()
    worded = any(k in hay for k in _APP_KEYWORDS)
    listed = bool(_BULK.search(body or ""))
    if names_tracked_company(sender, subject, jobs):
        return worded or not (listed or _AUTOMATED_SENDER.search(sender or ""))
    return worded and not listed


# Generic words that appear in many job titles — ignored when disambiguating
# which role at a company an email is about.
_ROLE_STOP = {
    "and", "the", "for", "with", "our", "you", "your", "are", "per", "job", "jobs",
    "role", "roles", "position", "positions", "team", "new", "work", "remote", "hybrid",
    "praha", "prague", "czech", "republic", "application", "received", "thank", "thanks",
    "applying", "apply", "re", "fwd", "has", "been", "update", "status",
}


def _role_tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{3,}", (text or "").lower()) if t not in _ROLE_STOP}


def _likelier(job: dict[str, Any]) -> tuple[int, int, str]:
    """When an email names no role and the company has several postings in the list, which one
    it is most likely about: a job you applied to before one you did not; among those, the one
    still open and furthest along (the company's next email continues that conversation, not a
    different application); then the one touched most recently. A rejected one comes last."""
    status = job.get("status", "found")
    applied = status in store.APPLICATION_STATUSES
    open_rank = 0 if status == "rejected" else RANK.get(status, 0)
    return (1 if applied else 0, open_rank if applied else 0, str(job.get("last_update") or ""))


def match_job(sender: str, subject: str, body: str, jobs: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Best-effort match an email to a tracked job.

    Word-level (not substring), and by words that are really the company's name. A company name found in the sender/subject counts
    far more than one found only deep in the body (so an Outlook/"Microsoft 365"
    footer in a Valeo email can't hijack the match). Among jobs at the same
    company, the one whose title best matches the subject wins — so "Application
    received for SW Tool Developer" links to that exact role, not a sibling
    posting at the same company.
    """
    strong = set(re.findall(r"[a-z0-9]{3,}", f"{sender} {subject}".lower()))
    weak = set(re.findall(r"[a-z0-9]{3,}", (body or "")[:1500].lower()))
    # words of the company's own name are not role words: "Interview with Brightline Robotics" must not
    # pick the company's "Robotics Software Engineer" posting. The sender's address shows the name.
    domain = sender_domain(sender).rsplit(".", 1)[0].replace(".", "")
    subj_role = {t for t in _role_tokens(subject) if t not in domain}
    best, best_key = None, (0, 0, 0, (0, 0, ""))
    for job in jobs:
        toks = company_tokens(job.get("company", ""))
        if not toks:
            continue
        # A word many companies share ("data", "international", "praha") names nobody: one of the
        # name's own words must be there, or, for a name made only of such words, all of it.
        own = toks - GENERIC_COMPANY_WORDS
        if own:
            if not own & (strong | weak):
                continue
        elif not toks <= (strong | weak):
            continue
        in_strong = len(toks & strong)
        in_weak = len(toks & weak)
        company_score = in_strong * 3 + in_weak
        role_score = len(_role_tokens(job.get("title", "")) & subj_role)
        key = (1 if in_strong else 0, company_score, role_score, _likelier(job))
        if key > best_key:
            best, best_key = job, key
    return best


def best_job_for_company_role(company: str, subject: str, jobs: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pick the tracked job that best fits a KNOWN company + an email subject.

    Used to re-link stored responses (whose company was already extracted) to the
    right job: among that company's postings, choose the title closest to the
    subject. Returns None if the company isn't tracked.
    """
    ctoks = company_tokens(company)
    if not ctoks:
        return None
    cands = [j for j in jobs if same_company(company, j.get("company", ""))]
    if not cands:
        return None
    subj_role = _role_tokens(subject) - ctoks        # the company's own name is not a role word
    return max(cands, key=lambda j: (len(_role_tokens(j.get("title", "")) & subj_role), _likelier(j)))
