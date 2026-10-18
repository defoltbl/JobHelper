"""Where "here" is for a search: the city, its country, and what counts as near enough.

Company career sites list a company's openings everywhere, so each one is asked whether it is
in the searched city, in the same country, or remote in a way that fits. Nothing is assumed
about which country that is: it is read from the city (for the larger cities of the countries
below) or taken from Options, where "Country" can be typed for any other place.

Which remote jobs fit is a choice in Options (`RemoteReach`): those open to people in your
country and in the countries you add, or remote jobs anywhere in the world.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable

# country: (how it is written in a posting's location, its larger cities with their other spellings)
COUNTRIES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "czechia": (("czech", "cesk", "czechia"), ("prague", "praha", "brno", "ostrava", "plzen", "pilsen", "olomouc", "liberec",
                                                 "pardubice", "hradec kralove", "ceske budejovice", "zlin")),
    "slovakia": (("slovak", "slovensk"), ("bratislava", "kosice", "zilina", "nitra")),
    "germany": (("germany", "deutschland"), ("berlin", "munich", "munchen", "hamburg", "frankfurt", "cologne", "koln", "stuttgart",
                                             "dusseldorf", "leipzig", "dresden", "nuremberg", "nurnberg", "hannover", "bremen")),
    "austria": (("austria", "osterreich"), ("vienna", "wien", "graz", "linz", "salzburg", "innsbruck")),
    "poland": (("poland", "polska"), ("warsaw", "warszawa", "krakow", "cracow", "wroclaw", "gdansk", "poznan", "lodz", "katowice")),
    "netherlands": (("netherlands", "nederland", "holland"), ("amsterdam", "rotterdam", "utrecht", "eindhoven", "the hague", "den haag")),
    "belgium": (("belgium", "belgie", "belgique"), ("brussels", "bruxelles", "antwerp", "ghent", "leuven")),
    "france": (("france",), ("paris", "lyon", "marseille", "toulouse", "lille", "nantes", "bordeaux")),
    "spain": (("spain", "espana"), ("madrid", "barcelona", "valencia", "seville", "sevilla", "malaga", "bilbao")),
    "portugal": (("portugal",), ("lisbon", "lisboa", "porto", "braga")),
    "italy": (("italy", "italia"), ("rome", "roma", "milan", "milano", "turin", "torino", "bologna", "florence", "naples")),
    "switzerland": (("switzerland", "schweiz", "suisse"), ("zurich", "geneva", "geneve", "basel", "bern", "lausanne")),
    "ireland": (("ireland",), ("dublin", "cork", "galway", "limerick")),
    "united kingdom": (("united kingdom", "england", "scotland", "wales", "great britain", "northern ireland"),
                       ("london", "manchester", "birmingham", "edinburgh", "glasgow", "leeds", "bristol", "cambridge", "oxford")),
    "sweden": (("sweden", "sverige"), ("stockholm", "gothenburg", "goteborg", "malmo")),
    "denmark": (("denmark", "danmark"), ("copenhagen", "kobenhavn", "aarhus")),
    "norway": (("norway", "norge"), ("oslo", "bergen", "trondheim")),
    "finland": (("finland", "suomi"), ("helsinki", "espoo", "tampere")),
    "hungary": (("hungary", "magyarorszag"), ("budapest", "debrecen", "szeged")),
    "romania": (("romania",), ("bucharest", "bucuresti", "cluj", "timisoara", "iasi")),
    "bulgaria": (("bulgaria",), ("sofia", "plovdiv", "varna")),
    "greece": (("greece", "hellas"), ("athens", "thessaloniki")),
    "croatia": (("croatia", "hrvatska"), ("zagreb", "split")),
    "slovenia": (("slovenia", "slovenija"), ("ljubljana", "maribor")),
    "serbia": (("serbia", "srbija"), ("belgrade", "beograd", "novi sad")),
    "ukraine": (("ukraine", "ukraina"), ("kyiv", "kiev", "lviv", "kharkiv", "odesa", "dnipro")),
    "estonia": (("estonia", "eesti"), ("tallinn", "tartu")),
    "latvia": (("latvia", "latvija"), ("riga",)),
    "lithuania": (("lithuania", "lietuva"), ("vilnius", "kaunas")),
    "united states": (("united states", "usa", "u.s."), ("new york", "san francisco", "seattle", "boston", "chicago", "austin",
                                                         "los angeles", "denver", "atlanta", "washington")),
    "canada": (("canada",), ("toronto", "vancouver", "montreal", "ottawa", "calgary")),
    "india": (("india",), ("bangalore", "bengaluru", "hyderabad", "mumbai", "pune", "chennai", "delhi", "gurgaon", "noida")),
    "australia": (("australia",), ("sydney", "melbourne", "brisbane", "perth")),
    "singapore": (("singapore",), ("singapore",)),
    "japan": (("japan",), ("tokyo", "osaka")),
    "brazil": (("brazil", "brasil"), ("sao paulo", "rio de janeiro")),
    "mexico": (("mexico",), ("mexico city", "guadalajara")),
    # ── the rest of the world: a posting that names one of these is tied to it ──
    "albania": (("albania",), ("tirana",)), "andorra": (("andorra",), ()), "armenia": (("armenia",), ("yerevan",)),
    "azerbaijan": (("azerbaijan",), ("baku",)), "belarus": (("belarus",), ("minsk",)),
    "bosnia and herzegovina": (("bosnia",), ("sarajevo",)), "cyprus": (("cyprus",), ("nicosia", "limassol")),
    "georgia": (("georgia", "sakartvelo"), ("tbilisi", "batumi")), "iceland": (("iceland",), ("reykjavik",)),
    "kosovo": (("kosovo",), ("pristina",)), "liechtenstein": (("liechtenstein",), ("vaduz",)),
    "luxembourg": (("luxembourg",), ()), "malta": (("malta",), ("valletta",)), "moldova": (("moldova",), ("chisinau",)),
    "monaco": (("monaco",), ()), "montenegro": (("montenegro",), ("podgorica",)),
    "north macedonia": (("north macedonia", "macedonia"), ("skopje",)), "russia": (("russia", "russian federation"), ("moscow",)),
    "san marino": (("san marino",), ()), "turkey": (("turkey", "turkiye"), ("istanbul", "ankara", "izmir")),
    "vatican city": (("vatican",), ()),
    "bahrain": (("bahrain",), ("manama",)), "iran": (("iran",), ("tehran",)), "iraq": (("iraq",), ("baghdad",)),
    "israel": (("israel",), ("tel aviv", "jerusalem", "haifa")), "jordan": (("jordan",), ("amman",)),
    "kuwait": (("kuwait",), ()), "lebanon": (("lebanon",), ("beirut",)), "oman": (("oman",), ("muscat",)),
    "palestine": (("palestine",), ("ramallah",)), "qatar": (("qatar",), ("doha",)),
    "saudi arabia": (("saudi arabia", "ksa"), ("riyadh", "jeddah")), "syria": (("syria",), ("damascus",)),
    "united arab emirates": (("united arab emirates", "uae"), ("dubai", "abu dhabi")), "yemen": (("yemen",), ()),
    "algeria": (("algeria",), ("algiers",)), "angola": (("angola",), ("luanda",)), "benin": (("benin",), ()),
    "botswana": (("botswana",), ("gaborone",)), "burkina faso": (("burkina faso",), ()), "burundi": (("burundi",), ()),
    "cameroon": (("cameroon",), ("douala", "yaounde")), "cape verde": (("cape verde", "cabo verde"), ()),
    "central african republic": (("central african republic",), ()), "chad": (("chad",), ()), "comoros": (("comoros",), ()),
    "congo": (("republic of the congo", "congo-brazzaville", "congo"), ("brazzaville",)),
    "dr congo": (("democratic republic of the congo", "dr congo", "drc"), ("kinshasa",)), "djibouti": (("djibouti",), ()),
    "egypt": (("egypt",), ("cairo", "alexandria")), "equatorial guinea": (("equatorial guinea",), ()),
    "eritrea": (("eritrea",), ()), "eswatini": (("eswatini", "swaziland"), ()), "ethiopia": (("ethiopia",), ("addis ababa",)),
    "gabon": (("gabon",), ()), "gambia": (("gambia",), ()), "ghana": (("ghana",), ("accra",)), "guinea": (("guinea",), ()),
    "guinea-bissau": (("guinea-bissau",), ()), "ivory coast": (("ivory coast", "cote d'ivoire", "cote divoire"), ("abidjan",)),
    "kenya": (("kenya",), ("nairobi",)), "lesotho": (("lesotho",), ()), "liberia": (("liberia",), ()), "libya": (("libya",), ()),
    "madagascar": (("madagascar",), ()), "malawi": (("malawi",), ()), "mali": (("mali",), ()),
    "mauritania": (("mauritania",), ()), "mauritius": (("mauritius",), ()), "morocco": (("morocco",), ("casablanca", "rabat")),
    "mozambique": (("mozambique",), ("maputo",)), "namibia": (("namibia",), ("windhoek",)), "niger": (("niger",), ()),
    "nigeria": (("nigeria",), ("lagos", "abuja")), "rwanda": (("rwanda",), ("kigali",)),
    "sao tome and principe": (("sao tome",), ()), "senegal": (("senegal",), ("dakar",)), "seychelles": (("seychelles",), ()),
    "sierra leone": (("sierra leone",), ()), "somalia": (("somalia",), ()),
    "south africa": (("south africa",), ("johannesburg", "cape town", "pretoria", "durban")),
    "south sudan": (("south sudan",), ()), "sudan": (("sudan",), ("khartoum",)), "tanzania": (("tanzania",), ("dar es salaam",)),
    "togo": (("togo",), ()), "tunisia": (("tunisia",), ("tunis",)), "uganda": (("uganda",), ("kampala",)),
    "zambia": (("zambia",), ("lusaka",)), "zimbabwe": (("zimbabwe",), ("harare",)),
    "afghanistan": (("afghanistan",), ()), "bangladesh": (("bangladesh",), ("dhaka",)), "bhutan": (("bhutan",), ()),
    "brunei": (("brunei",), ()), "cambodia": (("cambodia",), ("phnom penh",)),
    "china": (("china",), ("beijing", "shanghai", "shenzhen", "guangzhou", "hangzhou", "chengdu")),
    "hong kong": (("hong kong",), ()), "indonesia": (("indonesia",), ("jakarta", "bali")),
    "kazakhstan": (("kazakhstan",), ("almaty", "astana")), "kyrgyzstan": (("kyrgyzstan",), ("bishkek",)), "laos": (("laos",), ()),
    "malaysia": (("malaysia",), ("kuala lumpur", "penang")), "maldives": (("maldives",), ()),
    "mongolia": (("mongolia",), ("ulaanbaatar",)), "myanmar": (("myanmar", "burma"), ("yangon",)),
    "nepal": (("nepal",), ("kathmandu",)), "north korea": (("north korea",), ("pyongyang",)),
    "pakistan": (("pakistan",), ("karachi", "lahore", "islamabad")), "philippines": (("philippines",), ("manila", "cebu")),
    "south korea": (("south korea", "republic of korea", "korea"), ("seoul", "busan")),
    "sri lanka": (("sri lanka",), ("colombo",)), "taiwan": (("taiwan",), ("taipei",)), "tajikistan": (("tajikistan",), ()),
    "thailand": (("thailand",), ("bangkok",)), "timor-leste": (("timor-leste", "east timor"), ()),
    "turkmenistan": (("turkmenistan",), ()), "uzbekistan": (("uzbekistan",), ("tashkent",)),
    "vietnam": (("vietnam", "viet nam"), ("hanoi", "ho chi minh")),
    "new zealand": (("new zealand",), ("auckland", "wellington", "christchurch")), "fiji": (("fiji",), ()),
    "kiribati": (("kiribati",), ()), "marshall islands": (("marshall islands",), ()), "micronesia": (("micronesia",), ()),
    "nauru": (("nauru",), ()), "palau": (("palau",), ()), "papua new guinea": (("papua new guinea",), ()),
    "samoa": (("samoa",), ()), "solomon islands": (("solomon islands",), ()), "tonga": (("tonga",), ()),
    "tuvalu": (("tuvalu",), ()), "vanuatu": (("vanuatu",), ()),
    "antigua and barbuda": (("antigua",), ()), "argentina": (("argentina",), ("buenos aires", "cordoba")),
    "bahamas": (("bahamas",), ()), "barbados": (("barbados",), ()), "belize": (("belize",), ()),
    "bolivia": (("bolivia",), ("la paz",)), "chile": (("chile",), ("santiago de chile",)),
    "colombia": (("colombia",), ("bogota", "medellin")), "costa rica": (("costa rica",), ()), "cuba": (("cuba",), ("havana",)),
    "dominica": (("dominica",), ()), "dominican republic": (("dominican republic",), ("santo domingo",)),
    "ecuador": (("ecuador",), ("quito", "guayaquil")), "el salvador": (("el salvador",), ()), "grenada": (("grenada",), ()),
    "guatemala": (("guatemala",), ()), "guyana": (("guyana",), ()), "haiti": (("haiti",), ()), "honduras": (("honduras",), ()),
    "jamaica": (("jamaica",), ()), "nicaragua": (("nicaragua",), ()), "panama": (("panama",), ()),
    "paraguay": (("paraguay",), ("asuncion",)), "peru": (("peru",), ("lima",)), "puerto rico": (("puerto rico",), ("san juan",)),
    "saint kitts and nevis": (("saint kitts", "st. kitts", "st kitts"), ()),
    "saint lucia": (("saint lucia", "st. lucia", "st lucia"), ()),
    "saint vincent and the grenadines": (("saint vincent", "st. vincent", "st vincent"), ()), "suriname": (("suriname",), ()),
    "trinidad and tobago": (("trinidad",), ()), "uruguay": (("uruguay",), ("montevideo",)),
    "venezuela": (("venezuela",), ("caracas",)),
}

# The part of the world each country is in, for postings that name a region ("Remote - EMEA", "APAC").
_AREAS: dict[str, tuple[str, ...]] = {
    "europe": ("czechia", "slovakia", "germany", "austria", "poland", "netherlands", "belgium", "france", "spain", "portugal",
               "italy", "switzerland", "ireland", "united kingdom", "sweden", "denmark", "norway", "finland", "hungary", "romania",
               "bulgaria", "greece", "croatia", "slovenia", "serbia", "ukraine", "estonia", "latvia", "lithuania", "albania",
               "andorra", "armenia", "azerbaijan", "belarus", "bosnia and herzegovina", "cyprus", "georgia", "iceland", "kosovo",
               "liechtenstein", "luxembourg", "malta", "moldova", "monaco", "montenegro", "north macedonia", "russia",
               "san marino", "turkey", "vatican city"),
    "middle east": ("bahrain", "iran", "iraq", "israel", "jordan", "kuwait", "lebanon", "oman", "palestine", "qatar",
                    "saudi arabia", "syria", "united arab emirates", "yemen"),
    "africa": ("algeria", "angola", "benin", "botswana", "burkina faso", "burundi", "cameroon", "cape verde",
               "central african republic", "chad", "comoros", "congo", "dr congo", "djibouti", "egypt", "equatorial guinea",
               "eritrea", "eswatini", "ethiopia", "gabon", "gambia", "ghana", "guinea", "guinea-bissau", "ivory coast", "kenya",
               "lesotho", "liberia", "libya", "madagascar", "malawi", "mali", "mauritania", "mauritius", "morocco", "mozambique",
               "namibia", "niger", "nigeria", "rwanda", "sao tome and principe", "senegal", "seychelles", "sierra leone",
               "somalia", "south africa", "south sudan", "sudan", "tanzania", "togo", "tunisia", "uganda", "zambia", "zimbabwe"),
    "asia": ("india", "singapore", "japan", "afghanistan", "bangladesh", "bhutan", "brunei", "cambodia", "china", "hong kong",
             "indonesia", "kazakhstan", "kyrgyzstan", "laos", "malaysia", "maldives", "mongolia", "myanmar", "nepal",
             "north korea", "pakistan", "philippines", "south korea", "sri lanka", "taiwan", "tajikistan", "thailand",
             "timor-leste", "turkmenistan", "uzbekistan", "vietnam"),
    "oceania": ("australia", "new zealand", "fiji", "kiribati", "marshall islands", "micronesia", "nauru", "palau",
                "papua new guinea", "samoa", "solomon islands", "tonga", "tuvalu", "vanuatu"),
    "north america": ("united states", "canada"),
    "latin america": ("mexico", "brazil", "antigua and barbuda", "argentina", "bahamas", "barbados", "belize", "bolivia",
                      "chile", "colombia", "costa rica", "cuba", "dominica", "dominican republic", "ecuador", "el salvador",
                      "grenada", "guatemala", "guyana", "haiti", "honduras", "jamaica", "nicaragua", "panama", "paraguay",
                      "peru", "puerto rico", "saint kitts and nevis", "saint lucia", "saint vincent and the grenadines",
                      "suriname", "trinidad and tobago", "uruguay", "venezuela"),
}
AREA_OF = {country: area for area, members in _AREAS.items() for country in members}
EUROPE = set(_AREAS["europe"])
_NORTH_AFRICA = {"egypt", "libya", "tunisia", "algeria", "morocco"}
# Short codes a location may end with ("Brno, CZ"), matched as whole words only.
_CODES = {"czechia": "cz", "slovakia": "sk", "germany": "de", "austria": "at", "poland": "pl", "netherlands": "nl", "france": "fr",
          "spain": "es", "italy": "it", "united kingdom": "uk", "ireland": "ie", "switzerland": "ch", "sweden": "se",
          "hungary": "hu", "romania": "ro", "portugal": "pt", "belgium": "be", "denmark": "dk", "norway": "no", "finland": "fi",
          "united states": "us"}
# A region a posting may name, how it is written, and the countries in it.
_REGIONS: dict[str, tuple[str, set[str]]] = {
    "europe": (r"europe(?:an)?", EUROPE),
    "european union": (r"european union|\beu", EUROPE),
    "emea": (r"emea", EUROPE | set(_AREAS["middle east"]) | set(_AREAS["africa"])),
    "middle east": (r"middle east|mena", set(_AREAS["middle east"]) | _NORTH_AFRICA),
    "africa": (r"africa", set(_AREAS["africa"])),
    "asia": (r"asia", set(_AREAS["asia"])),
    "apac": (r"apac|asia[- ]pacific", set(_AREAS["asia"]) | set(_AREAS["oceania"])),
    "oceania": (r"oceania", set(_AREAS["oceania"])),
    "north america": (r"north america", set(_AREAS["north america"])),
    "americas": (r"americas", set(_AREAS["north america"]) | set(_AREAS["latin america"])),
    "latam": (r"latam|latin america|south america|central america", set(_AREAS["latin america"])),
}
_REGION_WORDS = {name: re.compile(rf"(?<![a-z])(?:{pattern})(?![a-z])") for name, (pattern, _) in _REGIONS.items()}
_REMOTE = re.compile(r"\b(remote|anywhere|worldwide|work from home|home office)\b")
# Words that hold a country's name without being about that country.
_NOT_A_COUNTRY = re.compile(r"\bnew mexico\b|\bnew jersey\b")
# How a country's name is written when it is shown; the others are its name with each word capitalised.
_SHOWN = {"dr congo": "DR Congo", "guinea-bissau": "Guinea-Bissau", "timor-leste": "Timor-Leste"}
_STEMS = {"czech", "cesk", "slovak", "slovensk"}      # "Czech Republic", "Ceska republika", "Slovakia", "Slovensko"
# Every way a country is written, longest first: "Papua New Guinea" is read before "Guinea", "South Sudan" before "Sudan".
_NAMES = sorted(((name, country) for country, (names, _) in COUNTRIES.items() for name in names), key=lambda nc: -len(nc[0]))


def _name_pattern(name: str) -> str:
    """A country's name as a whole word, except the few stems that have endings."""
    return rf"\b{re.escape(name)}" + ("" if name in _STEMS else r"\b")


def _named(names, text: str) -> bool:
    """Is one of a country's names in the text? As a whole word, except the few stems that have endings."""
    return any(re.search(_name_pattern(n), text) for n in names)


def plain(text: str) -> str:
    """Lower case without accents: "Kraków" and "krakow", "München" and "munchen" compare equal."""
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower().strip()


def shown(country: str) -> str:
    """A country as the window shows it: "united kingdom" is "United Kingdom", "dr congo" is "DR Congo"."""
    key = plain(country)
    return _SHOWN.get(key) or " ".join(w if w in ("and", "the", "of") else w.capitalize() for w in key.split())


def country_of(place: str) -> str:
    """The country a city or a country's name belongs to, by its name in `COUNTRIES`; '' when the app does not know it."""
    text = plain(place)
    if not text:
        return ""
    if text in COUNTRIES:
        return text
    for country, (names, cities) in COUNTRIES.items():
        if _named(names, text) or any(re.search(rf"\b{re.escape(c)}\b", text) for c in cities):
            return country
    return ""


def named_countries(location: str) -> set[str]:
    """Every known country a posting's location names, by itself, by a city or by a code."""
    text = _NOT_A_COUNTRY.sub(" ", plain(location))
    found = set()
    rest = text
    for name, country in _NAMES:                   # a longer name hides the shorter one inside it
        pattern = _name_pattern(name)
        if re.search(pattern, rest):
            found.add(country)
            rest = re.sub(pattern, " ", rest)
    for country, (_, cities) in COUNTRIES.items():
        code = _CODES.get(country)
        if any(re.search(rf"\b{re.escape(c)}\b", text) for c in cities) \
                or (code and re.search(rf"(?:,|\(|-)\s*{code}\b\)?\s*$", text)):
            found.add(country)
    if "georgia" in found and "united states" in found and not re.search(r"\b(tbilisi|batumi|sakartvelo)\b", text):
        found.discard("georgia")                   # "Atlanta, Georgia, United States" is the state
    return found


def named_regions(location: str) -> set[str]:
    """The parts of the world a posting's location names ("EMEA", "Remote - Europe")."""
    text = plain(location)
    return {name for name, words in _REGION_WORDS.items() if words.search(text)}


def is_remote(location: str) -> bool:
    """Does the location say the job is remote ("Remote", "Anywhere", "Home office")?"""
    return bool(_REMOTE.search(plain(location)))


def in_region(region: str, countries: Iterable[str]) -> bool:
    """Is one of these countries in that part of the world?"""
    members = _REGIONS[region][1]
    return any(c in members for c in countries)


class RemoteReach:
    """Which remote jobs a search keeps. Always: a job open to anyone, and a job tied to your country
    or to a country you added. A job tied to other countries ("USA Only", "Remote, South Korea") is
    never kept: it asks you to live or have the right to work there. For a job tied to a part of the
    world ("Remote – APAC"): "country" keeps it when your country or an added one is in it, "world"
    keeps it wherever it is. Options, the search and the window all read it from here."""

    SCOPES = (("country", "In my country"), ("world", "Anywhere in the world"))
    MAX_COUNTRIES = 40

    def __init__(self, scope: str = "country", countries: Iterable[str] = ()) -> None:
        self.scope = scope if scope in dict(self.SCOPES) else "country"
        self.countries = tuple(dict.fromkeys(c for c in (plain(x) for x in countries or ()) if c in COUNTRIES))

    @classmethod
    def from_options(cls, opts: dict[str, Any] | None) -> "RemoteReach":
        """From the saved Options; settings from before this choice existed keep the country rule."""
        opts = opts or {}
        countries = opts.get("remote_countries")
        return cls(str(opts.get("remote_where") or "country"), countries if isinstance(countries, list) else ())

    @property
    def worldwide(self) -> bool:
        return self.scope == "world"

    def open_to(self, home: str) -> set[str]:
        """The countries a remote job may be tied to: your own and the ones you added."""
        return ({home} if home else set()) | set(self.countries)

    def allows(self, location: str, home: str) -> bool:
        """For a remote job: is it open to you? One that names no place is open to anyone."""
        named, regions = named_countries(location), named_regions(location)
        allowed = self.open_to(home)
        if named:                                   # tied to countries: one of them must be yours or added
            return bool(named & allowed)
        if not regions or self.worldwide:
            return True
        return any(not home or in_region(r, allowed) for r in regions)

    def as_options(self) -> dict[str, Any]:
        return {"remote_where": self.scope, "remote_countries": list(self.countries)}

    @classmethod
    def problem(cls, opts: dict[str, Any]) -> str:
        """What is wrong with the remote-jobs part of Options as sent ('' = nothing). Only the keys present are checked."""
        if "remote_where" in opts and opts["remote_where"] not in dict(cls.SCOPES):
            return "“Remote jobs” must be in your country or anywhere in the world."
        if "remote_countries" not in opts:
            return ""
        picked = opts["remote_countries"]
        if not isinstance(picked, (list, tuple)) or any(not isinstance(c, str) for c in picked):
            return "“Remote jobs” takes a list of countries."
        if len(picked) > cls.MAX_COUNTRIES:
            return f"“Remote jobs” takes up to {cls.MAX_COUNTRIES} countries."
        unknown = next((c for c in picked if plain(c) not in COUNTRIES), None)
        return f"“{unknown[:40]}” is not a country the app knows. Choose it from the list." if unknown is not None else ""

    @classmethod
    def offered(cls) -> dict[str, Any]:
        """What the window offers: the two choices, the parts of the world to filter the country list by, and the most countries."""
        return {"scopes": [{"key": key, "name": name} for key, name in cls.SCOPES],
                "areas": [{"key": "", "name": "All"}] + [{"key": area, "name": shown(area)} for area in _AREAS],
                "most": cls.MAX_COUNTRIES}


def all_countries() -> list[dict[str, Any]]:
    """Every country the app knows, by name, for the window's country picker: [{key, name, area, names}]. `names` are
    the other ways the app recognises it ("usa", "england", "czech"), so typing one of them finds the country too."""
    return sorted(({"key": c, "name": shown(c), "area": AREA_OF.get(c, ""),
                    "names": [n for n in dict.fromkeys(COUNTRIES[c][0]) if n != c]} for c in COUNTRIES), key=lambda c: c["name"])


def fits(location: str, where: str, country: str = "", reach: RemoteReach | None = None, remote: bool = False) -> bool:
    """Is a posting with this location one for someone searching in `where`?

    Yes when the location is unknown, names the city, names the same country (by name, by one
    of its cities, or as free text when the country is one the app has no table for), or names a
    region that country is in ("Europe", "EMEA"). A remote job (`remote`: from a remote board,
    which may not say so) fits as `reach` decides; without it, as the country rule decides.
    `country` is what Options says; empty means "the country of the city"."""
    loc = plain(location)
    if not loc:
        return True
    city = plain(where)
    home = country_of(country) or country_of(where)
    typed = plain(country)
    if city and city in loc:
        return True
    if typed and not home and typed in loc:                 # a country the app has no table for: as it was typed
        return True
    if remote or _REMOTE.search(loc):
        return (reach or RemoteReach()).allows(location, home)
    if home and home in named_countries(location):
        return True
    return any(not home or in_region(r, {home}) for r in named_regions(location))
