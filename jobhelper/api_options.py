"""Options and the career-site list: reading, checking and saving them, and the figures read from them.

Part of the window's back end: the facade `ui_api.Api` hands calls to this service."""
from __future__ import annotations

import json
import re

from . import trouble
from . import chrome
from . import agent1_cv, details, filters, scrapers_ats, config, followup, housekeeping, integrity, places, salary, textfmt, vault


class OptionsService:
    """Options and the career-site list: reading, checking and saving them, and the figures read from them."""

    def __init__(self, app, editor, cv, desktop) -> None:
        """`app` is the facade (`ui_api.Api`): what this service needs from the others is asked through it."""
        self._app, self._editor, self._cv, self._desktop = app, editor, cv, desktop

    # ── one job in full ─────────────────────────────────────────
    def followup_days(self) -> int:
        return followup.saved_days()

    def profession_fields(self, wanted=None):
        """Which professions the free first look treats as yours, for the roles given (the ones
        typed in Options, before they are saved): {fields: [...], from_cv: bool}."""
        from . import prefilter
        try:
            profile = agent1_cv.load_profile() or {}
        except Exception:  # noqa: BLE001 - no CV analysis yet
            profile = {}
        wanted = [str(w).strip() for w in (wanted or []) if str(w).strip()] or list(profile.get("target_roles") or [])
        roles = wanted + list(profile.get("adjacent_roles") or [])
        from_roles = prefilter.fields_of(roles)
        return {"fields": from_roles or prefilter.fields_of([], self._cv.text()), "from_cv": not from_roles, "all": list(prefilter.FIELDS)}

    def currencies(self):
        return list(salary.CURRENCIES)

    def about_you(self):
        """What the About you window shows: the saved values, and what the app says about them (about_you.AboutYou)."""
        from . import about_you, details
        o = self.options()
        page = about_you.AboutYou(o).page(details.load(), agent1_cv.seniority())
        return {**{k: o.get(k) for k in about_you.KEYS}, **page, "currencies": list(salary.CURRENCIES)}

    def work_notes_size(self, jobs, general):
        """How long the notes are as the app reads them (WorkNotes.size), for the window's live count."""
        from . import about_you
        return about_you.WorkNotes([j for j in (jobs or []) if isinstance(j, dict)], str(general or "")).size()

    def save_about_you(self, data):
        """Save only the About you facts; the other Options stay as they are."""
        from . import about_you
        sent = {k: v for k, v in (data or {}).items() if k in about_you.KEYS} if isinstance(data, dict) else {}
        if not sent:
            return {"ok": False, "msg": "Nothing to save."}
        return self.save_options(sent)

    def start_preview(self, text):
        """The date forms will get for "You can start" (about_you.AboutYou.start_preview)."""
        from . import about_you
        return about_you.AboutYou.start_preview(text)

    def country_of(self, city):
        """The country the app takes a city to be in ("Czechia"), or '' when it does not know the city."""
        name = places.country_of(str(city or ""))
        return places.shown(name) if name else ""

    def countries(self):
        """Every country the app knows, for the remote-jobs country picker: [{key, name, area, names}] by name."""
        return places.all_countries()

    def remote_choices(self):
        """What Options and the country picker offer for remote jobs (places.RemoteReach.offered)."""
        return places.RemoteReach.offered()

    # ── the last run (shown on the Last run card, also after a restart) ──
    def last_run(self):
        """The Last run card: {} when there is none, or it cannot be read (the card is only a summary)."""
        try:
            data = config.LAST_RUN.read()
        except vault.VaultError:
            data = None
        return data if isinstance(data, dict) else {}

    def note_run(self, **fields):
        """Merge the given facts into the saved last-run summary."""
        data = self.last_run()
        data.update({k: v for k, v in fields.items() if v is not None})
        config.LAST_RUN.load_for_change()           # a damaged summary is kept aside, never written over
        config.LAST_RUN.write(data)
        return data

    # ── read / write: options ───────────────────────────────────
    def options(self):
        # Seed the search keywords from the CV profile so the user sees (and can
        # edit) what's actually being searched.
        try:
            profile = agent1_cv.load_profile() or {}
            seed_queries = profile.get("search_queries") or profile.get("target_roles") or []
            level = agent1_cv.level_of(profile)
            target_roles = [str(r) for r in (profile.get("target_roles") or [])]
        except Exception:
            seed_queries, level, target_roles = [], "junior", []
        defaults = {"where": "", "country": "", "salary_target": 0, "salary_currency": "CZK", "salary_by_role": [], "source": "czech", "include_remote": False, "full_time_only": True,
                    "all_languages": False, "max_age_days": config.MAX_JOB_AGE_DAYS,
                    "threshold": config.DEFAULT_THRESHOLD, "min_lead_score": config.MIN_LEAD_SCORE,
                    "model": config.MODEL, "per_query": 15, "queries": list(seed_queries),
                    "followup_days": followup.DEFAULT_DAYS, "scan_days": config.IMAP_LOOKBACK_DAYS,
                    "skip_words": ["intern", "internship"], "keep_words": [],
                    # what the scorer treats as your direction: starts from the roles read from your CV
                    "wanted_roles": list(target_roles), "unwanted_roles": [], "my_fields": [],
                    # start from the level in the CV; the user can change both in Options
                    "level_words": filters.default_level_words(level), "max_years": filters.default_max_years(level),
                    "about_right_to_work": "", "about_start": "", "about_experience": "", "notifications": True, "scan_all_folders": False, "assistant_watch": False, "assistant_browser": "chrome", "text_size": 100,
                    "keep_backups": housekeeping.DEFAULT_KEEP}
        try:
            if config.UI_SETTINGS.exists():                   # a file that holds no settings (null, a list) is noted below
                defaults.update(config.UI_SETTINGS.load())
        except Exception as e:  # noqa: BLE001 - the defaults are used; the start-up check tells the user
            trouble.note("reading the saved Options", e)
        from . import job_sources
        choice = job_sources.SourceChoice.from_options(defaults)        # also reads the older one-source settings
        defaults["sources"], defaults["source_names"] = list(choice.kinds), choice.names()   # the names: the main screen's chips
        defaults.update(places.RemoteReach.from_options(defaults).as_options())       # which remote jobs fit
        return defaults

    MAX_SALARY, MAX_PAY_ROWS = details.MAX_SALARY, 20   # the highest figure (My details' own); kinds of role with a figure of their own
    OPTION_NUMBERS = {"salary_target": (0, MAX_SALARY), "threshold": (0, 100), "min_lead_score": (0, 100), "max_age_days": (0, 3650), "per_query": (1, 100),
                      "max_years": (0, 60), "keep_backups": (0, 1000), "followup_days": (0, 365), "scan_days": (1, 3650)}
    OPTION_LISTS = ("queries", "skip_words", "keep_words", "level_words", "wanted_roles", "unwanted_roles", "my_fields")
    OPTION_TEXTS = {"where": 80, "country": 60, "about_right_to_work": 300, "about_start": 300, "about_experience": config.MAX_EXPERIENCE_NOTES}
    MAX_LIST, MAX_WORD = 60, 100
    MAX_COMPANY_NAME, MAX_PAY_ROLE = 60, 60          # a career site's name; a kind of role under "salary by role"
    MODELS = ("sonnet", "opus", "haiku")
    SOURCES = ("czech", "linkedin", "remote", "careers", "adzuna", "jooble", "all")

    def check_options(self, opts):
        """(clean options, '') or ({}, what is wrong). The window checks the same things as you type;
        this is the last word, so nothing unusable is saved whatever sent it."""
        if not isinstance(opts, dict):
            return {}, "Those are not Options."
        clean = dict(opts)
        clean.pop("source_names", None)          # worked out from the sources when read, never stored
        if "sources" in clean:
            from . import job_sources
            picked = clean["sources"]
            if not isinstance(picked, (list, tuple)) or not picked:
                return {}, "Choose at least one job source."
            if any(not job_sources.SourceChoice.known(k) for k in picked):
                return {}, "That is not a job source the app knows."
            clean["sources"] = list(job_sources.SourceChoice(picked).kinds)
        for key, (low, high) in self.OPTION_NUMBERS.items():
            if key in clean:
                value = clean[key]
                if isinstance(value, bool) or not isinstance(value, (int, float)) or value != int(value) or not low <= value <= high:
                    return {}, f"“{key.replace('_', ' ')}” must be a whole number from {low} to {high}."
                clean[key] = int(value)
        for key in self.OPTION_LISTS:
            if key in clean:
                if not isinstance(clean[key], (list, tuple)):
                    return {}, f"“{key.replace('_', ' ')}” must be a list of words."
                words = [str(w).strip() for w in clean[key] if isinstance(w, str) and str(w).strip()]
                if len(words) > self.MAX_LIST:
                    return {}, f"“{key.replace('_', ' ')}” has {len(words)} entries; the most is {self.MAX_LIST}."
                long = next((w for w in words if len(w) > self.MAX_WORD), None)
                if long:
                    return {}, f"An entry under “{key.replace('_', ' ')}” is {len(long)} characters long; the most is {self.MAX_WORD}."
                clean[key] = list(dict.fromkeys(words))
        for key, limit in self.OPTION_TEXTS.items():
            if key in clean:
                text = str(clean[key] or "").strip() if isinstance(clean[key], (str, type(None))) else None
                if text is None:
                    return {}, f"“{key.replace('_', ' ')}” must be text."
                if len(text) > limit:
                    return {}, f"“{key.replace('_', ' ')}” is {len(text)} characters long; the most is {limit}. Shorten it."
                clean[key] = text
        if "salary_by_role" in clean:
            entries = clean["salary_by_role"]
            if not isinstance(entries, (list, tuple)):
                return {}, "“salary by role” must be a list."
            tidy = []
            for entry in entries:
                role = str((entry or {}).get("role") or "").strip() if isinstance(entry, dict) else ""
                amount = (entry or {}).get("amount") if isinstance(entry, dict) else None
                problem = self.pay_problem(role, amount, [t["role"] for t in tidy])
                if problem:
                    return {}, problem
                tidy.append({"role": role, "amount": int(amount)})
            clean["salary_by_role"] = tidy
        if "about_jobs" in clean:                  # the work notes per job: WorkNotes owns their rules
            from . import about_you
            if not isinstance(clean["about_jobs"], (list, tuple)) or not all(isinstance(n, dict) for n in clean["about_jobs"]):
                return {}, "“about jobs” must be a list of notes."
            general = clean.get("about_experience", config.ui_settings().get("about_experience", ""))
            notes = about_you.WorkNotes(list(clean["about_jobs"]), str(general or ""))
            if notes.problem():
                return {}, notes.problem()
            clean["about_jobs"] = notes.as_options()["about_jobs"]
        if "salary_currency" in clean:
            code = str(clean["salary_currency"] or "").strip().upper()
            if code not in salary.CURRENCIES:
                return {}, "“salary currency” must be one of: " + ", ".join(salary.CURRENCIES) + "."
            clean["salary_currency"] = code
        if "text_size" in clean:
            if isinstance(clean["text_size"], bool) or clean["text_size"] not in config.TEXT_SIZES:
                return {}, "“size of text and controls” must be one of: " + ", ".join(f"{n}%" for n in config.TEXT_SIZES) + "."
            clean["text_size"] = int(clean["text_size"])
        for key, allowed in (("model", self.MODELS), ("source", self.SOURCES)):
            if key in clean and (not isinstance(clean[key], str) or clean[key] not in allowed):
                return {}, f"“{key}” must be one of: " + ", ".join(allowed) + "."
        if "assistant_browser" in clean and (not isinstance(clean["assistant_browser"], str) or clean["assistant_browser"] not in chrome.BROWSERS):
            return {}, "“assistant browser” must be one of: " + ", ".join(chrome.BROWSERS) + "."
        if clean.get("country") and not re.fullmatch(r"[^\W\d_]+(?:[ '.\-]+[^\W\d_]+)*\.?", clean["country"]):
            return {}, "“country” must be a country's name in letters, for example Germany."
        remote_problem = places.RemoteReach.problem(clean)
        if remote_problem:
            return {}, remote_problem
        if "remote_countries" in clean:
            clean["remote_countries"] = list(places.RemoteReach("country", clean["remote_countries"]).countries)
        for key in ("include_remote", "all_languages", "full_time_only", "notifications", "scan_all_folders", "assistant_watch"):
            if key in clean and not isinstance(clean[key], bool):
                return {}, f"“{key.replace('_', ' ')}” must be on or off."
        return clean, ""

    @staticmethod
    def pay_key(role) -> str:
        """Two lines of "A different figure for" are the same kind of role when these words are equal."""
        return " ".join(str(role or "").split()).lower()

    @staticmethod
    def own_figure(estimate_czk, currency) -> int:
        """An estimate (always in crowns) as a figure of your own in the currency you chose."""
        return salary.from_czk(float(estimate_czk or 0), str(currency or "CZK"))

    def pay_problem(self, role, amount, others=()):
        """'' or what is wrong with one line of "A different figure for": the words the window shows when you press Add, and
        the save check of every line (one rule for both)."""
        role = " ".join(str(role or "").split())
        if not role:
            return "Enter a kind of role in words, for example support."
        if textfmt.has_non_latin(role):
            return "Write the kind of role in English (Latin letters), as it stands in job titles."
        if not 2 <= len(role) <= self.MAX_PAY_ROLE or not re.search(r"[^\W\d_]{2}", role):
            return "Enter a kind of role in words, for example support."
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount != int(amount) or not 1 <= amount <= self.MAX_SALARY:
            return f"Enter the salary for “{role}”: a whole number above 0."
        if self.pay_key(role) in [self.pay_key(o) for o in others]:
            return f"“{role}” is already in the list: change its figure there."
        if len(others) >= self.MAX_PAY_ROWS:
            return f"The list takes up to {self.MAX_PAY_ROWS} kinds of role. Remove one first."
        return ""

    def save_options(self, opts):
        """Save the Options. What the window does not send (the chosen master CV) is kept."""
        clean, problem = self.check_options(opts or {})
        if problem:
            return {"ok": False, "msg": problem}
        kept = {k: v for k, v in config.ui_settings().items() if k not in clean}
        config.save_ui_settings({**kept, **clean})
        return {"ok": True}

    # ── career-site companies (data/companies.json) ─────────────
    def companies(self):
        p = config.DATA_DIR / "companies.json"
        try:
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
                return [{"name": c.get("name", ""), "ats": c.get("ats", ""), "token": c.get("token", "")}
                        for c in data if isinstance(c, dict) and c.get("ats") and c.get("token")]
        except Exception as e:  # noqa: BLE001 - an unreadable list is shown as empty
            trouble.note("reading the career-site list", e)
        return []

    def save_companies(self, companies):
        config.ensure_dirs()
        # The token becomes part of an address the app asks (https://<token>.recruitee.com …): only a plain slug is kept,
        # so nothing typed or pasted here can send a request anywhere else. The window checks the same as you type.
        clean = [{"name": " ".join(str(c.get("name") or c["token"]).split())[:self.MAX_COMPANY_NAME], "ats": c["ats"], "token": c["token"]}
                 for c in (companies if isinstance(companies, (list, tuple)) else [])
                 if isinstance(c, dict) and isinstance(c.get("ats"), str) and c["ats"] in scrapers_ats.ATS_NAMES
                 and isinstance(c.get("token"), str) and scrapers_ats.is_token(c["token"])][:200]
        (config.DATA_DIR / "companies.json").write_text(
            json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
        integrity.approve(["companies"])          # changed through the app: trusted
        return {"ok": True, "count": len(clean)}
