"""
Canonical company naming.

Broker descriptions ("ALPHABET INC-CL C") are too long to display and, worse,
defeat the dashboard's name normaliser — so a position silently loses its
fundamentals and quality scores because its name no longer matches
the key those tables are stored under.

Names are canonicalised once, on import, and the ISIN is stored alongside as the
stable identity: a later renaming by the broker then cannot orphan a holding.
"""

from __future__ import annotations

import re
import unicodedata

# Where the generic cleaner gives a poor or ambiguous result. Keyed by ISIN,
# the one identifier that survives renamings and venue changes.
COMPANY_NAME_BY_ISIN = {
    "US02079K1079": "Alphabet",
    "US92826C8394": "Visa",
    "US67066G1040": "Nvidia",
    "GB0002634946": "BAE Systems",
    "NL0012969182": "Adyen",
    "DE0007030009": "Rheinmetall",
    "KYG875721634": "Tencent",
    "US5324571083": "Eli Lilly",
    "NL0011585146": "Ferrari",
    "GB0009895292": "AstraZeneca",
}

# Markers carrying no company identity: depositary receipts and share classes.
_NAME_NOISE = [
    r"/\s*THE$",                                      # "COCA-COLA CO/THE"
    r"\s*-\s*(?:SPON(?:SORED)?|UNSPON(?:SORED)?|SP|ADR|ADS)\b.*$",
    r"\s*-\s*CL(?:ASS)?\s+[A-Z]\b.*$",                # "-CL C", "-CLASS A SHARES"
    r"\s*-\s*[A-H]$",                                 # "-H" (H shares), "-A"
    r"\b(?:SPON(?:SORED)?|UNSPON(?:SORED)?|ADR|ADS)\b",
    r"\bCL(?:ASS)?\s+[A-Z]\b",
    r"\bSHARES?\b",
]

_LEGAL_FORMS = (
    r"\b(?:INC|INCORPORATED|CORP|CORPORATION|PLC|NV|BV|SE|SPA|SAS|ASA|OYJ|KGAA|"
    r"LTD|LIMITED|LLC|PTE|CO|COMPANY|HOLDINGS?|GROUP|SAB\s+DE\s+CV)\b\.?"
)

# Left uppercase rather than title-cased.
_ACRONYMS = {"AI", "ADR", "NV", "SA", "AG", "PLC", "BAE", "SPDR",
             "HP", "RBOB", "WTI", "PCCW", "ASE", "BOC", "CK", "DBS", "SAP", "AXA", "CSX"}


def canonical_company_name(description: str, isin: str | None = None) -> str:
    """Shorten a broker description into a short, consistently cased name."""
    if isin:
        override = COMPANY_NAME_BY_ISIN.get(isin.strip().upper())
        if override:
            return override
    if not description:
        return description

    s = description.strip()
    for pattern in _NAME_NOISE:
        s = re.sub(pattern, " ", s, flags=re.I)
    s = re.sub(_LEGAL_FORMS, " ", s, flags=re.I)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[\s,&/-]+$", "", s).strip()
    if not s:
        return description.strip()

    words = []
    for w in s.split():
        if w.upper() in _ACRONYMS:
            words.append(w.upper())
        elif w.isupper() and len(w) <= 3:
            # Short all-caps tokens are initialisms ("SK", "US", "AI"), not
            # words that want title-casing into "Sk".
            words.append(w)
        elif w.isupper():
            words.append("-".join(part.capitalize() for part in w.split("-")))
        else:
            words.append(w)
    return " ".join(words)


# Bonds carry a coupon ("TREASURY 3.15% 2031") and commodity lines are not
# companies — neither should be put through the company cleaner.
_BOND_RX = re.compile(r"\d+\.\d+\s*%")
_COUNTER_RX = re.compile(r"\s*\(\s*\d+\s*\)\s*$")


def display_name(name: str, isin: str | None = None) -> str:
    """
    Cleaner for names coming from ETF holdings data, where sources spell the
    same company several ways ("Samsung Electronics Co., Ltd." vs "Samsung
    Electronics"). Display-only: the stored scrape is left untouched.
    """
    if not name or _BOND_RX.search(name):
        return name
    # The scraper marks genuinely separate lines (preferred vs common shares)
    # with a trailing counter. Keep it, or the two lines collapse into one.
    counter = ""
    m = _COUNTER_RX.search(name)
    if m:
        counter = " " + m.group(0).strip()
        name = name[:m.start()]
    cleaned = canonical_company_name(name, isin)
    # Never let the cleaner empty out a name that was only a legal form.
    return (cleaned or name.strip()) + counter


# ─────────────────────────────────────────────────────────────────────────────
# Company key
#
# A faithful port of the browser's normalizeName()/companyKey(). The fundamentals
# and quality tables are keyed by this value and read back by the front end, so
# the two implementations MUST agree — the aliases below are served to the
# browser in /reference.js rather than duplicated there, so they cannot drift.
# ─────────────────────────────────────────────────────────────────────────────

# Bridges normalisation cannot reach on its own: abbreviations and renamings.
NAME_ALIASES = {
    "taiwan semiconductor manufacturing": "taiwan semicon mfg",
    "taiwan semiconductor": "taiwan semicon mfg",
    "tsmc": "taiwan semicon mfg",
    "nestle n": "nestle",
    # SMGB lists "AMD", VUSA "Advanced Micro Devices": one company, two rows.
    "advanced micro devices": "amd",
}

_LEGAL_TOKENS = (r"\b(corp|corporation|inc|incorporated|ltd|limited|plc|co|company|ag|nv|bv|sa|se|"
                 r"spa|sas|ab|asa|oyj|kgaa|pte|llc|lp|publ|ser|holdings|holding|group|adr|ads|com)\b")
_CLASS_RX = re.compile(r"\s+(?:cl(?:ass)?\s+)?([A-C](?:/[A-C])?)$", re.I)


def normalize_name(n: str) -> str:
    """Port of the front end's normalizeName()."""
    if not n:
        return ""
    if _BOND_RX.search(n):          # bonds carry a coupon; leave them alone
        return n.lower()

    m = _CLASS_RX.search(n)
    class_suffix = " " + m.group(1).upper() if m else ""
    s = n[:m.start()] if m else n

    s = s.lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\.com\b", "", s)
    # Drop descriptive parentheticals but keep the scraper's numeric counters.
    s = re.sub(r"\s*\((?!\s*\d+\s*\))[^)]*\)", "", s)
    s = s.replace(".", "")
    s = re.sub(r"[,\-]", " ", s)
    s = re.sub(_LEGAL_TOKENS, "", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"[\s&.,;:_\-]+$", "", s)
    return NAME_ALIASES.get(s, s) + class_suffix


def company_key(n: str) -> str:
    """Port of the front end's companyKey(): collapses share classes and counters."""
    s = normalize_name(n)
    s = re.sub(r"\s*\(\s*\d+\s*\)\s*$", "", s)
    s = re.sub(r"\s+[A-C](/[A-C])?$", "", s)
    return s.strip()


# ─────────────────────────────────────────────────────────────────────────────
# Commodity classification
#
# Commodity ETFs hold futures, not companies, so they have no Yahoo "sector".
# Labelling them by commodity type keeps the Sector column meaningful instead of
# leaving a fifth of the exposure table blank.
# ─────────────────────────────────────────────────────────────────────────────

COMMODITY_SECTORS = {
    # Precious metals
    "gold": "Precious Metals", "silver": "Precious Metals",
    "platinum": "Precious Metals", "palladium": "Precious Metals",
    # Industrial metals
    "copper": "Industrial Metals", "aluminum": "Industrial Metals",
    "aluminium": "Industrial Metals", "zinc": "Industrial Metals",
    "nickel": "Industrial Metals", "lead": "Industrial Metals",
    "tin": "Industrial Metals", "iron ore": "Industrial Metals",
    # Energy
    "wti crude oil": "Oil & Gas", "brent crude": "Oil & Gas",
    "natural gas": "Oil & Gas", "heating oil": "Oil & Gas",
    "gas oil": "Oil & Gas", "rbob gasoline": "Oil & Gas",
    "gasoline": "Oil & Gas", "crude oil": "Oil & Gas",
    # Agriculture
    "corn": "Agriculture", "wheat": "Agriculture", "kansas wheat": "Agriculture",
    "soybeans": "Agriculture", "soybean oil": "Agriculture",
    "soybean meal": "Agriculture", "sugar": "Agriculture",
    "coffee": "Agriculture", "cotton": "Agriculture", "cocoa": "Agriculture",
    # Livestock
    "live cattle": "Livestock", "lean hogs": "Livestock",
    "feeder cattle": "Livestock",
}


# Private additions (.data/reference.json, git-ignored). See local.py.
import local  # noqa: E402

local.merge("COMPANY_NAME_BY_ISIN", COMPANY_NAME_BY_ISIN)
local.merge("NAME_ALIASES", NAME_ALIASES)
local.merge("NAME_ACRONYMS", _ACRONYMS)
