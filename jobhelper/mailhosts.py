"""Which mail server a mailbox is read from, and what kind of password it takes.

The server is known for the common providers and is read from the address. For any other
address (a company's or a small provider's) the person types the IMAP server once. Two
providers cannot be read with a password at all, and the app says so instead of failing later.
"""
from __future__ import annotations

import re

APP_PASSWORD = "an app password made in the account's security settings, not your normal password"

# domain: (IMAP server, what to enter as the password)
PROVIDERS: dict[str, tuple[str, str]] = {
    "gmail.com": ("imap.gmail.com", "a Google App Password (16 letters), not your normal password"),
    "googlemail.com": ("imap.gmail.com", "a Google App Password (16 letters), not your normal password"),
    "yahoo.com": ("imap.mail.yahoo.com", APP_PASSWORD), "yahoo.co.uk": ("imap.mail.yahoo.com", APP_PASSWORD),
    "yahoo.de": ("imap.mail.yahoo.com", APP_PASSWORD), "yahoo.fr": ("imap.mail.yahoo.com", APP_PASSWORD),
    "ymail.com": ("imap.mail.yahoo.com", APP_PASSWORD), "aol.com": ("imap.aol.com", APP_PASSWORD),
    "icloud.com": ("imap.mail.me.com", "an app-specific password from your Apple account, not your normal password"),
    "me.com": ("imap.mail.me.com", "an app-specific password from your Apple account, not your normal password"),
    "mac.com": ("imap.mail.me.com", "an app-specific password from your Apple account, not your normal password"),
    "fastmail.com": ("imap.fastmail.com", APP_PASSWORD), "fastmail.fm": ("imap.fastmail.com", APP_PASSWORD),
    "zoho.com": ("imap.zoho.com", APP_PASSWORD), "zohomail.eu": ("imap.zoho.eu", APP_PASSWORD),
    "gmx.com": ("imap.gmx.com", "your mailbox password, with IMAP turned on in the mailbox settings"),
    "gmx.net": ("imap.gmx.net", "your mailbox password, with IMAP turned on in the mailbox settings"),
    "gmx.de": ("imap.gmx.net", "your mailbox password, with IMAP turned on in the mailbox settings"),
    "web.de": ("imap.web.de", "your mailbox password, with IMAP turned on in the mailbox settings"),
    "seznam.cz": ("imap.seznam.cz", "your mailbox password, with IMAP turned on in the mailbox settings"),
    "email.cz": ("imap.seznam.cz", "your mailbox password, with IMAP turned on in the mailbox settings"),
    "post.cz": ("imap.seznam.cz", "your mailbox password, with IMAP turned on in the mailbox settings"),
    "centrum.cz": ("imap.centrum.cz", "your mailbox password"), "wp.pl": ("imap.wp.pl", "your mailbox password"),
    "o2.pl": ("poczta.o2.pl", "your mailbox password"), "mail.com": ("imap.mail.com", "your mailbox password"),
    "ukr.net": ("imap.ukr.net", "the IMAP password made in the mailbox settings, not your normal password"),
}
# Mailboxes a program cannot read with a password, with what to do instead.
NOT_POSSIBLE = {
    **dict.fromkeys(("outlook.com", "hotmail.com", "live.com", "msn.com", "outlook.cz", "hotmail.co.uk"),
                    "Microsoft no longer lets a program read an Outlook.com mailbox with a password. Forward your job mail to another "
                    "mailbox and connect that one, or paste replies into their applications by hand."),
    **dict.fromkeys(("proton.me", "protonmail.com", "pm.me"),
                    "Proton Mail can only be read through its own Bridge program, which this app does not use. Forward your job mail "
                    "to another mailbox and connect that one, or paste replies into their applications by hand."),
}
_HOST = re.compile(r"(?=.{4,253}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+", re.IGNORECASE)
MAX_PASSWORD = 128


def domain_of(address: str) -> str:
    return str(address or "").strip().lower().rpartition("@")[2]


def is_gmail(address: str, host: str = "") -> bool:
    return (host or "").strip().lower() == "imap.gmail.com" or domain_of(address) in ("gmail.com", "googlemail.com")


def server_for(address: str, typed: str = "") -> dict[str, object]:
    """Where this address is read from: {host, known, gmail, hint, problem}.

    `typed` is the server the person entered (it wins over what the app knows, so a company
    mailbox hosted by Google can be given imap.gmail.com). `problem` is set when nothing can be
    done yet: the provider cannot be read, the server is missing, or it is not a server name."""
    domain, typed = domain_of(address), str(typed or "").strip().lower()
    out = {"host": "", "known": False, "gmail": False, "hint": "", "problem": ""}
    if domain in NOT_POSSIBLE and not typed:
        return {**out, "known": True, "problem": NOT_POSSIBLE[domain]}
    if typed:
        if not _HOST.fullmatch(typed):
            return {**out, "problem": "That is not a mail server's name. It looks like imap.example.com: letters, digits, dots and hyphens."}
        gmail = is_gmail(address, typed)
        return {**out, "host": typed, "known": domain in PROVIDERS, "gmail": gmail,
                "hint": "Use " + (PROVIDERS["gmail.com"][1] if gmail else "the password your mail provider gives for reading mail by IMAP") + "."}
    if domain in PROVIDERS:
        host, password = PROVIDERS[domain]
        return {**out, "host": host, "known": True, "gmail": host == "imap.gmail.com", "hint": f"Read from {host}. Use {password}."}
    if not domain:
        return out
    return {**out, "problem": "",
            "hint": "The app does not know this provider. Enter its IMAP server (your provider's help pages name it), "
                    "for example imap." + domain + "."}


def password_problem(address: str, host: str, password: str) -> str:
    """'' or what is wrong with the password as typed, before any server is asked."""
    text = str(password or "")
    if not text.strip():
        return "Enter the password for that address."
    if is_gmail(address, host):
        if not re.fullmatch(r"[a-z]{16}", re.sub(r"\s+", "", text), re.IGNORECASE):
            return "A Google App Password is 16 letters (no digits). Check for typos."
        return ""
    if len(text) > MAX_PASSWORD:
        return f"The password is {len(text)} characters long; the most is {MAX_PASSWORD}."
    if not text.isascii():
        return "A mail server takes only English letters, digits and symbols in a password here. Make an app password, which has only those."
    return ""
