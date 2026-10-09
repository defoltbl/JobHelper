"""Where "here" is for a search: the city, its country, and what counts as near enough.

Company career sites list a company's openings everywhere, so each one is asked whether it is
in the searched city, in the same country, or remote in a way that fits. Nothing is assumed
about which country that is: it is read from the city (for the larger cities of the countries
below) or taken from Options, where "Country" can be typed for any other place.
"""
from __future__ import annotations

import re
import unicodedata

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
}
_OUTSIDE_EUROPE = {"united states", "canada", "india", "australia", "singapore", "japan", "brazil", "mexico"}
EUROPE = set(COUNTRIES) - _OUTSIDE_EUROPE
# Short codes a location may end with ("Brno, CZ"), matched as whole words only.
_CODES = {"czechia": "cz", "slovakia": "sk", "germany": "de", "austria": "at", "poland": "pl", "netherlands": "nl", "france": "fr",
          "spain": "es", "italy": "it", "united kingdom": "uk", "ireland": "ie", "switzerland": "ch", "sweden": "se",
          "hungary": "hu", "romania": "ro", "portugal": "pt", "belgium": "be", "denmark": "dk", "norway": "no", "finland": "fi",
          "united states": "us"}
_REGIONS = {"europe": EUROPE, "emea": EUROPE, "european union": EUROPE,
            "north america": {"united states", "canada"}, "americas": {"united states", "canada", "brazil", "mexico"},
            "latam": {"brazil", "mexico"}, "apac": {"india", "australia", "singapore", "japan"}}
_REMOTE = re.compile(r"\b(remote|anywhere|worldwide|work from home|home office)\b")
_EU = re.compile(r"\beu\b")


_STEMS = {"czech", "cesk", "slovak", "slovensk"}      # "Czech Republic", "Ceska republika", "Slovakia", "Slovensko"


def _named(names, text: str) -> bool:
    """Is one of a country's names in the text? As a whole word, except the few stems that have endings."""
    return any(re.search(rf"\b{re.escape(n)}" + ("" if n in _STEMS else r"\b"), text) for n in names)


def plain(text: str) -> str:
    """Lower case without accents: "Kraków" and "krakow", "München" and "munchen" compare equal."""
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower().strip()


def country_of(place: str) -> str:
    """The country a city or a country's name belongs to, by its name in `COUNTRIES`; '' when the app does not know it."""
    text = plain(place)
    if not text:
        return ""
    for country, (names, cities) in COUNTRIES.items():
        if text == country or _named(names, text) or \
                any(re.search(rf"\b{re.escape(c)}\b", text) for c in cities):
            return country
    return ""


def named_countries(location: str) -> set[str]:
    """Every known country a posting's location names, by itself, by a city or by a code."""
    text = plain(location)
    found = set()
    for country, (names, cities) in COUNTRIES.items():
        code = _CODES.get(country)
        if _named(names, text) or any(re.search(rf"\b{re.escape(c)}\b", text) for c in cities) \
                or (code and re.search(rf"(?:,|\(|-)\s*{code}\b\)?\s*$", text)):
            found.add(country)
    return found


def fits(location: str, where: str, country: str = "") -> bool:
    """Is a posting with this location one for someone searching in `where`?

    Yes when the location is unknown, names the city, names the same country (by name, by one
    of its cities, or as free text when the country is one the app has no table for), names a
    region that country is in ("Europe", "EMEA"), or is remote without being tied to another
    part of the world. `country` is what Options says; empty means "the country of the city"."""
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
    named = named_countries(location)
    if home and home in named:
        return True
    regions = {name for name in _REGIONS if name in loc} | ({"european union"} if _EU.search(loc) else set())
    if any(not home or home in _REGIONS[name] for name in regions):
        return True
    if _REMOTE.search(loc):
        # remote, but pinned to somewhere else ("Remote, US", "Remote - APAC") is not for here
        return not named and not regions
    return False
