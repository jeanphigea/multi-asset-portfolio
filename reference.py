"""
Reference data: sector taxonomy, benchmarks, company profiles, scenarios and
instrument symbols. Static by design; each block carries its own as-of date.

The exposure table carries three different kinds of sector label:

  * curated shorthand in COMPANY_ESTIMATES ("Big Tech", "Semis", "Defence")
  * Yahoo's own classification            ("Technology", "Financial Services")
  * commodity types                       ("Precious Metals", "Agriculture")

None of those line up with the GICS sectors a benchmark is published under, so
comparing the portfolio with an index means first mapping everything onto one
taxonomy. GICS is the common denominator, since that is what MSCI publishes.
"""

from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# MSCI World sector weights
#
# STATIC REFERENCE DATA — these are approximate published index weights, not a
# live feed, and they drift as markets move. Update MSCI_WORLD_AS_OF whenever
# you refresh them from the MSCI World factsheet; the UI shows that date so the
# figures are never mistaken for something current.
# ─────────────────────────────────────────────────────────────────────────────
MSCI_WORLD_AS_OF = "2026-03"
MSCI_WORLD_SOURCE = "MSCI World Index factsheet (GICS sectors), approximate"

MSCI_WORLD_SECTORS = {
    "Information Technology": 26.0,
    "Financials":             16.0,
    "Industrials":            11.0,
    "Consumer Discretionary": 10.5,
    "Health Care":            10.0,
    "Communication Services":  8.0,
    "Consumer Staples":         6.0,
    "Energy":                   4.0,
    "Materials":                3.5,
    "Utilities":                2.8,
    "Real Estate":              2.2,
}

# The 11 GICS sectors, in the order charts and tables should present them.
GICS_ORDER = list(MSCI_WORLD_SECTORS) + ["Commodities", "Cash & Money Market", "Unclassified"]

# Yahoo's sector names -> GICS. Yahoo is close to GICS but renames four.
GICS_FROM_YAHOO = {
    "technology":              "Information Technology",
    "financial services":      "Financials",
    "healthcare":              "Health Care",
    "health care":             "Health Care",
    "consumer cyclical":       "Consumer Discretionary",
    "consumer defensive":      "Consumer Staples",
    "basic materials":         "Materials",
    "communication services":  "Communication Services",
    "industrials":             "Industrials",
    "energy":                  "Energy",
    "utilities":               "Utilities",
    "real estate":             "Real Estate",
}

# The dashboard's curated shorthand -> GICS, used only where Yahoo has nothing.
# These follow GICS's own classification of the companies concerned, which is
# not always the intuitive reading: Alphabet and Netflix are Communication
# Services, Amazon and Tesla are Consumer Discretionary.
GICS_FROM_LABEL = {
    "big tech":          "Information Technology",
    "software":          "Information Technology",
    "semis":             "Information Technology",
    "semiconductors":    "Information Technology",
    "payments":          "Financials",
    "banks":             "Financials",
    "insurance":         "Financials",
    "financial":         "Financials",
    "conglomerate":      "Industrials",
    "defence":           "Industrials",
    "defense":           "Industrials",
    "industrials":       "Industrials",
    "rail":              "Industrials",
    "pharma":            "Health Care",
    "healthtech":        "Health Care",
    "biotech":           "Health Care",
    "luxury auto":       "Consumer Discretionary",
    "auto":              "Consumer Discretionary",
    "autoev":            "Consumer Discretionary",
    "housebuilder":      "Consumer Discretionary",
    "retail":            "Consumer Discretionary",
    "china tech":        "Consumer Discretionary",
    "media":             "Communication Services",
    "telecom":           "Communication Services",
    "consumer staples":  "Consumer Staples",
    "oil & gas":         "Energy",
    "oil and gas":       "Energy",
    "mining":            "Materials",
    "materials":         "Materials",
    "chemicals":         "Materials",
    "utilities":         "Utilities",
    "reit":              "Real Estate",
    "real estate":       "Real Estate",
    # Labels COMPANY_ESTIMATES uses that had no mapping, so those rows fell through
    # to "Unclassified" whenever Yahoo had no sector for them.
    "midstream":         "Energy",
    "auto/ev":           "Consumer Discretionary",
    "holding co":        "Industrials",
}
# A label that already IS a GICS sector name maps to itself ("Financials").
GICS_FROM_LABEL.update({s.lower(): s for s in MSCI_WORLD_SECTORS})


# ─────────────────────────────────────────────────────────────────────────────
# Curated company profiles: GICS sector + country, keyed by company_key().
#
# Covers every company the demo's look-through reaches (as of 2026-10),
# so the exposure table, the sector pies and the country view never depend on a
# fundamentals refresh having run. Yahoo's own sector still wins where it maps
# (see gicsSector in static/app.js); for country, this table wins, because Yahoo reports the
# head-office country, which is not how index providers classify a company
# (Tencent's HQ is Shenzhen but it is incorporated in the Cayman Islands —
# both MSCI and this table call it China).
#
# Country follows MSCI's classification where it is unambiguous; otherwise the
# country of primary listing and incorporation.
# ─────────────────────────────────────────────────────────────────────────────
_IT, _FIN, _HC, _CD, _CS = ("Information Technology", "Financials", "Health Care",
                            "Consumer Discretionary", "Consumer Staples")
_IND, _COM, _EN, _MAT, _UT, _RE = ("Industrials", "Communication Services", "Energy",
                                   "Materials", "Utilities", "Real Estate")
CASH_SECTOR = "Cash & Money Market"
US, UK, CA = "United States", "United Kingdom", "Canada"
KR, TW, CN, HK = "South Korea", "Taiwan", "China", "Hong Kong"
AU, SG, CH, FR = "Australia", "Singapore", "Switzerland", "France"
DE, NL, IN, NZ = "Germany", "Netherlands", "India", "New Zealand"

COMPANY_PROFILES_AS_OF = "2026-10"
COMPANY_PROFILES = {
    # ── United States ─────────────────────────────────────────────────────────
    "alphabet": (_COM, US), "microsoft": (_IT, US), "amazon": (_CD, US), "eli lilly": (_HC, US),
    "apple": (_IT, US), "nvidia": (_IT, US), "coca cola": (_CS, US), "netflix": (_COM, US),
    "visa": (_FIN, US), "mastercard": (_FIN, US), "broadcom": (_IT, US),
    "exxonmobil": (_EN, US), "micron technology": (_IT, US), "amd": (_IT, US),
    "advanced micro devices": (_IT, US), "intel": (_IT, US), "applied materials": (_IT, US),
    "lam research": (_IT, US), "nextera energy": (_UT, US), "union pacific": (_IND, US),
    "texas instruments": (_IT, US), "meta platforms": (_COM, US), "southern": (_UT, US),
    "duke energy": (_UT, US), "csx": (_IND, US), "williams companies": (_EN, US),
    "american tower": (_RE, US), "tesla": (_CD, US), "norfolk southern": (_IND, US),
    "american electric power": (_UT, US), "berkshire hathaway": (_FIN, US),
    "kinder morgan": (_EN, US), "dominion energy": (_UT, US), "targa resources": (_EN, US),
    "cheniere energy": (_EN, US), "oneok": (_EN, US), "sempra": (_UT, US),
    "johnson & johnson": (_HC, US), "jpmorgan chase": (_FIN, US), "entergy": (_UT, US),
    "xcel energy": (_UT, US), "exelon": (_UT, US), "caterpillar": (_IND, US),
    "walmart": (_CS, US), "consolidated edison": (_UT, US),
    "public service enterprise": (_UT, US), "costco wholesale": (_CS, US),
    "cisco systems": (_IT, US), "abbvie": (_HC, US), "tjx companies": (_CD, US),
    "kla": (_IT, US), "merck": (_HC, US),
    # ── Canada ────────────────────────────────────────────────────────────────
    "enbridge": (_EN, CA), "tc energy": (_EN, CA), "canadian pacific kansas city": (_IND, CA),
    "canadian national railway": (_IND, CA),
    # ── Latin America ─────────────────────────────────────────────────────────
    "vale": (_MAT, "Brazil"),
    "ishares msci brazil ucits etf de": (None, "Brazil"),  # a fund inside EMIM
    # ── United Kingdom ────────────────────────────────────────────────────────
    "astrazeneca": (_HC, UK), "bae systems": (_IND, UK), "national grid": (_UT, UK),
    # ── Europe ex-UK ──────────────────────────────────────────────────────────
    "ferrari": (_CD, "Italy"), "rheinmetall": (_IND, DE), "totalenergies": (_EN, FR),
    "adyen": (_FIN, NL), "asml": (_IT, NL), "roche": (_HC, CH), "iberdrola": (_UT, "Spain"),
    # ── Asia Pacific ──────────────────────────────────────────────────────────
    "samsung electronics": (_IT, KR), "sk hynix": (_IT, KR), "sk square": (_IND, KR),
    "samsung electro mechanics": (_IT, KR), "hyundai motor": (_CD, KR),
    "taiwan semicon mfg": (_IT, TW), "mediatek": (_IT, TW), "delta electronics": (_IT, TW),
    "hon hai precision": (_IT, TW), "ase technology": (_IT, TW), "yageo": (_IT, TW),
    "elite material": (_IT, TW), "united microelectronics": (_IT, TW), "alibaba": (_CD, CN),
    "tencent": (_COM, CN), "china construction bank": (_FIN, CN),
    "industrial and commercial bank of china": (_FIN, CN), "xiaomi": (_IT, CN),
    "boc hong kong": (_FIN, HK), "power assets": (_UT, HK), "ck asset": (_RE, HK),
    "henderson land development": (_RE, HK), "pccw": (_COM, HK), "sino land": (_RE, HK),
    "swire pacific": (_IND, HK), "ck infrastructure": (_UT, HK), "honda motor": (_CD, "Japan"),
    "persol": (_IND, "Japan"), "bhp": (_MAT, AU), "fortescue": (_MAT, AU), "santos": (_EN, AU),
    "anz": (_FIN, AU), "westpac banking": (_FIN, AU), "qbe insurance": (_FIN, AU),
    "sonic healthcare": (_HC, AU), "insurance australia": (_FIN, AU), "dbs": (_FIN, SG),
    "oversea chinese banking": (_FIN, SG), "united overseas bank": (_FIN, SG),
    "wilmar international": (_CS, SG), "venture": (_IT, SG), "spark new zealand": (_COM, NZ),
    "ebos": (_HC, NZ), "hdfc bank": (_FIN, IN), "icici bank": (_FIN, IN),
    "reliance industries": (_EN, IN), "bharti airtel": (_COM, IN),
    # CSH2 is a money-market fund: cash, not an equity, and not a country bet.
    "amundi smart overnight return gbp hedged": (CASH_SECTOR, "Cash"),
}

# Region + MSCI market class per country. "Commodities" and "Cash" are
# deliberately not countries: they are shown, but outside the comparison.
COUNTRY_META = {
    "United States": ("North America", "DM"), "Canada": ("North America", "DM"),
    "Brazil": ("Latin America", "EM"), "Argentina": ("Latin America", "Frontier"),
    "Mexico": ("Latin America", "EM"),
    "United Kingdom": ("Europe", "DM"), "France": ("Europe", "DM"),
    "Germany": ("Europe", "DM"), "Netherlands": ("Europe", "DM"),
    "Switzerland": ("Europe", "DM"), "Italy": ("Europe", "DM"), "Spain": ("Europe", "DM"),
    "Sweden": ("Europe", "DM"), "Denmark": ("Europe", "DM"), "Ireland": ("Europe", "DM"),
    "Belgium": ("Europe", "DM"), "Finland": ("Europe", "DM"), "Norway": ("Europe", "DM"),
    "Japan": ("Asia Pacific", "DM"), "Australia": ("Asia Pacific", "DM"),
    "Hong Kong": ("Asia Pacific", "DM"), "Singapore": ("Asia Pacific", "DM"),
    "New Zealand": ("Asia Pacific", "DM"),
    "China": ("Asia Pacific", "EM"), "Taiwan": ("Asia Pacific", "EM"),
    "South Korea": ("Asia Pacific", "EM"), "India": ("Asia Pacific", "EM"),
    "South Africa": ("Middle East & Africa", "EM"),
    "Saudi Arabia": ("Middle East & Africa", "EM"), "Israel": ("Middle East & Africa", "DM"),
    "Commodities": ("Non-equity", "—"), "Cash": ("Non-equity", "—"),
}

# MSCI ACWI country weights — STATIC, approximate, same caveats as the sector
# weights above. ACWI rather than World because the portfolio holds emerging
# markets (EMIM, the Asia Pacific dividend fund), which World excludes.
MSCI_ACWI_AS_OF = "2026-03"
MSCI_ACWI_SOURCE = "MSCI ACWI Index factsheet (country weights), approximate"
MSCI_ACWI_COUNTRIES = {
    "United States": 63.5, "Japan": 4.8, "United Kingdom": 3.2, "China": 3.0,
    "Canada": 2.9, "France": 2.3, "Taiwan": 2.3, "Germany": 2.1, "Switzerland": 2.1,
    "India": 1.8, "Australia": 1.6, "South Korea": 1.3, "Netherlands": 1.1,
    "Sweden": 0.8, "Italy": 0.7, "Spain": 0.7, "Denmark": 0.6, "Brazil": 0.5,
    "Hong Kong": 0.5, "Singapore": 0.4, "Saudi Arabia": 0.4, "South Africa": 0.3,
    "Mexico": 0.2, "New Zealand": 0.05, "Other": 2.85,
}


# ─────────────────────────────────────────────────────────────────────────────
# Risk tab: benchmarks, currencies and stress scenarios
#
# Everything below is ASSUMPTION, not data. The historical metrics on the Risk
# tab come from real prices; the forward-looking scenarios are judgement calls,
# written down here so they can be read, argued with and edited in one place.
# ─────────────────────────────────────────────────────────────────────────────

# Used for Sharpe/Sortino and as the return on cash-like holdings (CSH2), whose
# own price history is too short. Approximate UK Bank Rate; edit as it moves.
RISK_FREE_RATE = 4.0

# Cash-like positions: priced like any holding when marking to market, but
# modelled as earning RISK_FREE_RATE in the history and as 0% in a GBP crash.
CASH_TICKERS = {"CSH2"}

_EM = {c for c, (_, m) in COUNTRY_META.items() if m in ("EM", "Frontier")}
_world = {c: w for c, w in MSCI_ACWI_COUNTRIES.items() if c not in _EM and c != "Other"}
_world = {c: round(w / sum(_world.values()) * 100, 2) for c, w in _world.items()}

# Each benchmark needs two descriptions: a GBP-quoted ETF for the historical
# metrics, and an approximate sector / country / theme mix so a hypothetical
# scenario can be applied to it with the same rules as the portfolio.
# `tags` are the % of the index in each theme the scenarios single out.
BENCHMARKS = {
    "acwi": {"name": "MSCI ACWI", "ticker": "SSAC.L",
             "note": "iShares MSCI ACWI (SSAC), in GBP",
             "sectors": MSCI_WORLD_SECTORS, "countries": MSCI_ACWI_COUNTRIES,
             "tags": {"semis": 11, "ai_megacap": 22, "banks": 7, "gold_miners": 0.5,
                      "defence": 1.5, "autos": 2, "bitcoin": 0.1}},
    "world": {"name": "MSCI World", "ticker": "SWDA.L",
              "note": "iShares Core MSCI World (SWDA), in GBP",
              "sectors": MSCI_WORLD_SECTORS, "countries": _world,
              "tags": {"semis": 10, "ai_megacap": 24, "banks": 7, "gold_miners": 0.5,
                       "defence": 1.5, "autos": 2, "bitcoin": 0.1}},
    "sp500": {"name": "S&P 500", "ticker": "VUSA.L",
              "note": "Vanguard S&P 500 (VUSA), in GBP",
              "sectors": {"Information Technology": 34, "Financials": 13, "Consumer Discretionary": 10.5,
                          "Communication Services": 10, "Health Care": 9, "Industrials": 8.5,
                          "Consumer Staples": 5.5, "Energy": 3, "Utilities": 2.5,
                          "Real Estate": 2, "Materials": 2},
              "countries": {"United States": 100},
              "tags": {"semis": 13, "ai_megacap": 33, "banks": 4.5, "defence": 2, "autos": 2, "bitcoin": 0.2}},
    "ftse100": {"name": "FTSE 100", "ticker": "ISF.L",
                "note": "iShares Core FTSE 100 (ISF), in GBP",
                "sectors": {"Financials": 23, "Consumer Staples": 15, "Industrials": 13, "Health Care": 12,
                            "Energy": 11, "Consumer Discretionary": 8, "Materials": 7,
                            "Communication Services": 4, "Utilities": 4, "Information Technology": 1.5,
                            "Real Estate": 1.5},
                "countries": {"United Kingdom": 100},
                "tags": {"banks": 9, "defence": 3, "gold_miners": 1.5}},
    "nasdaq100": {"name": "Nasdaq 100", "ticker": "EQQQ.L",
                  "note": "Invesco EQQQ Nasdaq-100, in GBP",
                  "sectors": {"Information Technology": 50, "Communication Services": 16,
                              "Consumer Discretionary": 14, "Health Care": 6, "Consumer Staples": 5,
                              "Industrials": 5, "Utilities": 1.5, "Materials": 1.2, "Energy": 0.5,
                              "Financials": 0.5, "Real Estate": 0.3},
                  "countries": {"United States": 100},
                  "tags": {"semis": 25, "ai_megacap": 45, "autos": 3, "bitcoin": 0.5}},
}

# Currency each country's equities are priced in, for the FX leg of a scenario.
# A scenario quotes FX as the move of that currency against GBP; anything it does
# not name falls back to its group ("EM", "commodity_fx"), then to 0.
COUNTRY_CCY = {
    "United States": "USD", "Canada": "CAD", "Argentina": "USD", "Brazil": "BRL", "Mexico": "MXN",
    "United Kingdom": "GBP", "France": "EUR", "Germany": "EUR", "Netherlands": "EUR", "Italy": "EUR",
    "Spain": "EUR", "Ireland": "EUR", "Belgium": "EUR", "Finland": "EUR", "Switzerland": "CHF",
    "Sweden": "SEK", "Denmark": "DKK", "Norway": "NOK", "Japan": "JPY", "Australia": "AUD",
    "New Zealand": "NZD", "Hong Kong": "USD",   # HKD is pegged to the dollar
    "Singapore": "SGD", "China": "CNY", "Taiwan": "TWD", "South Korea": "KRW", "India": "INR",
    "South Africa": "ZAR", "Saudi Arabia": "USD", "Israel": "ILS",
    "Commodities": "USD", "Cash": "GBP", "Other": "EM",
}
CCY_GROUP = {"CAD": "commodity_fx", "AUD": "commodity_fx", "NZD": "commodity_fx", "NOK": "commodity_fx",
             "BRL": "EM", "MXN": "EM", "CNY": "EM", "TWD": "EM", "KRW": "EM", "INR": "EM",
             "ZAR": "EM", "SGD": "EM", "ILS": "EM", "SEK": "EUR", "DKK": "EUR"}

# Companies treated as the AI mega-cap trade (tag "ai_megacap").
AI_MEGACAPS = ["alphabet", "microsoft", "amazon", "meta platforms", "apple", "nvidia", "broadcom", "tesla"]

# ── Forward-looking stress scenarios, plausible as of 2026-10 ────────────────
# Model, per holding (all figures in %):
#   local = market + sectors[GICS sector] + countries[country] + Σ tags[theme]
#   GBP return = (1 + local) × (1 + fx[currency vs GBP]) − 1
# Commodities take commodities[type] instead of the equity terms; cash is 0%.
# A benchmark gets the same terms through its sector / country / theme weights.
# Sizes are calibrated to the named historical analogues, not forecasts.
SCENARIOS_AS_OF = "2026-10"
SCENARIOS = [
    {"key": "ai_bust", "name": "AI capex bust",
     "horizon": "3–9 months", "analog": "Dot-com bust 2000–02; DeepSeek day, Jan 2025",
     "story": "Hyperscalers cut AI capex after monetisation disappoints. Semiconductors and the AI "
              "mega-caps de-rate hard, the AI-power trade unwinds, and money rotates into defensives.",
     "market": -15,
     "sectors": {"Information Technology": -10, "Communication Services": -6, "Utilities": -8,
                 "Industrials": -4, "Consumer Discretionary": -3, "Consumer Staples": 10, "Health Care": 8,
                 "Financials": 3, "Real Estate": 4, "Materials": 3, "Energy": 2},
     "countries": {"Taiwan": -12, "South Korea": -10, "Netherlands": -5, "United States": -4,
                   "Japan": -2, "United Kingdom": 6, "Switzerland": 5},
     "tags": {"semis": -15, "ai_megacap": -10, "bitcoin": -30},
     "commodities": {"Precious Metals": 5, "Oil & Gas": -10, "Industrial Metals": -12, "Agriculture": 0, "Livestock": 0},
     "fx": {"USD": -3, "JPY": 5, "CHF": 4, "EUR": 0, "EM": -3, "commodity_fx": -3}},
    {"key": "hard_landing", "name": "US hard landing and credit event",
     "horizon": "6–12 months", "analog": "2008 financial crisis (milder); COVID crash, Feb–Mar 2020",
     "story": "US recession arrives with private-credit and commercial-property defaults. Credit spreads "
              "blow out, cyclicals and banks sell off, the dollar and yen rally as safe havens.",
     "market": -25,
     "sectors": {"Financials": -10, "Consumer Discretionary": -8, "Energy": -8, "Real Estate": -8,
                 "Industrials": -5, "Materials": -5, "Information Technology": -3, "Communication Services": -2,
                 "Health Care": 10, "Consumer Staples": 12, "Utilities": 8},
     "countries": {"United Kingdom": 2, "Germany": -3, "Brazil": -8, "South Korea": -5, "Taiwan": -5,
                   "China": -3, "India": -3, "Australia": -3},
     "tags": {"banks": -10, "autos": -8, "semis": -8, "bitcoin": -35, "gold_miners": 15, "defence": 5},
     "commodities": {"Precious Metals": 10, "Oil & Gas": -30, "Industrial Metals": -20, "Agriculture": -8, "Livestock": -5},
     "fx": {"USD": 6, "JPY": 10, "CHF": 8, "EUR": 1, "EM": -6, "commodity_fx": -8}},
    {"key": "bond_revolt", "name": "Bond-market revolt and inflation comeback",
     "horizon": "3–6 months", "analog": "2022 rate shock (S&P 500 −25%, Nasdaq −35%)",
     "story": "Sticky inflation and US deficits push the 10-year Treasury past 6%. Long-duration "
              "growth stocks and property de-rate; energy and banks hold up; trust in the dollar slips.",
     "market": -16,
     "sectors": {"Information Technology": -8, "Communication Services": -6, "Consumer Discretionary": -6,
                 "Real Estate": -12, "Utilities": -8, "Health Care": -2, "Industrials": -2,
                 "Consumer Staples": 2, "Financials": 4, "Energy": 8, "Materials": 3},
     "countries": {"United States": -3, "United Kingdom": -4, "Brazil": -6, "India": -4, "Japan": 2},
     "tags": {"ai_megacap": -6, "semis": -6, "bitcoin": -30, "gold_miners": 8, "banks": 3},
     "commodities": {"Precious Metals": 6, "Oil & Gas": 10, "Industrial Metals": 5, "Agriculture": 8, "Livestock": 4},
     "fx": {"USD": -4, "CHF": 6, "JPY": 3, "EUR": 2, "EM": -5, "commodity_fx": 0}},
    {"key": "taiwan", "name": "Taiwan Strait crisis",
     "horizon": "1–6 months", "analog": "No close analogue; Russia sanctions shock, Feb–Mar 2022",
     "story": "A Chinese quarantine of Taiwan halts leading-edge chip supply and triggers sanctions. "
              "Asian markets and semiconductors crash; defence, gold and oil rise.",
     "market": -20,
     "sectors": {"Information Technology": -12, "Consumer Discretionary": -6, "Communication Services": -4,
                 "Materials": -4, "Financials": -3, "Industrials": -3, "Real Estate": -2,
                 "Energy": 6, "Consumer Staples": 3, "Health Care": 3, "Utilities": 2},
     "countries": {"Taiwan": -35, "China": -25, "Hong Kong": -20, "South Korea": -15, "Japan": -10,
                   "Singapore": -8, "Australia": -6, "Netherlands": -5, "Germany": -3,
                   "United Kingdom": 4, "Switzerland": 3, "India": 3, "Brazil": 2},
     "tags": {"semis": -18, "defence": 30, "autos": -10, "ai_megacap": -6, "gold_miners": 18, "bitcoin": -15},
     "commodities": {"Precious Metals": 18, "Oil & Gas": 20, "Industrial Metals": -10, "Agriculture": 8, "Livestock": 0},
     "fx": {"USD": 7, "CHF": 9, "JPY": 2, "EUR": -1, "EM": -8, "commodity_fx": -6}},
    {"key": "hormuz", "name": "Gulf conflict and oil shock",
     "horizon": "1–4 months", "analog": "Gulf War 1990 (−20%); energy shock 2022",
     "story": "Conflict with Iran closes the Strait of Hormuz and Brent goes above $130. Energy "
              "importers and consumer stocks suffer, producers and defence gain, and markets fear stagflation.",
     "market": -12,
     "sectors": {"Energy": 25, "Consumer Discretionary": -10, "Industrials": -6, "Information Technology": -4,
                 "Real Estate": -4, "Consumer Staples": -3, "Financials": -3, "Materials": -2,
                 "Communication Services": -2, "Utilities": -2},
     "countries": {"India": -10, "Japan": -6, "South Korea": -6, "China": -5, "Taiwan": -4, "Germany": -5,
                   "Italy": -4, "Spain": -4, "France": -3, "Netherlands": -3, "United Kingdom": 2,
                   "Norway": 10, "Canada": 6, "Brazil": 6, "Argentina": 5, "United States": 1},
     "tags": {"defence": 12, "autos": -8, "gold_miners": 10, "bitcoin": -10},
     "commodities": {"Precious Metals": 10, "Oil & Gas": 55, "Industrial Metals": -6, "Agriculture": 8, "Livestock": 3},
     "fx": {"USD": 4, "CHF": 5, "JPY": -3, "EUR": -3, "EM": -6, "commodity_fx": 3}},
    {"key": "trade_war", "name": "Global tariff war escalation",
     "horizon": "2–6 months", "analog": "Tariff shock, Feb–Apr 2025 (S&P 500 −19%)",
     "story": "Broad US tariffs return with retaliation from China and Europe. Supply chains, autos and "
              "exporters take the hit; the dollar weakens as in April 2025, and gold rallies.",
     "market": -15,
     "sectors": {"Consumer Discretionary": -8, "Industrials": -6, "Materials": -6, "Information Technology": -6,
                 "Energy": -6, "Financials": -3, "Consumer Staples": 4, "Health Care": 3, "Utilities": 5,
                 "Communication Services": 1},
     "countries": {"China": -15, "Hong Kong": -10, "Mexico": -15, "South Korea": -10, "Taiwan": -8,
                   "Japan": -8, "Germany": -8, "Canada": -8, "Italy": -4, "France": -4, "Netherlands": -4,
                   "Australia": -4, "United States": -3, "Switzerland": -2, "India": -2, "Brazil": -2,
                   "United Kingdom": 1},
     "tags": {"autos": -12, "semis": -6, "gold_miners": 10, "defence": 2},
     "commodities": {"Precious Metals": 8, "Oil & Gas": -12, "Industrial Metals": -15, "Agriculture": -10, "Livestock": -3},
     "fx": {"USD": -3, "CHF": 5, "JPY": 4, "EUR": 2, "EM": -5, "commodity_fx": -5}},
    {"key": "crypto", "name": "Crypto collapse",
     "horizon": "1–3 months", "analog": "Crypto winter 2022 (Bitcoin −65%, MicroStrategy −74%)",
     "story": "An exchange failure or regulatory crackdown sends Bitcoin down 60%. Leveraged bitcoin "
              "holders are forced to sell; the wider market barely notices.",
     "market": -4,
     "sectors": {"Information Technology": -1, "Financials": -1},
     "countries": {}, "tags": {"bitcoin": -60},
     "commodities": {"Precious Metals": 2},
     "fx": {"USD": 1}},
    {"key": "gilt_crisis", "name": "UK gilt and sterling crisis",
     "horizon": "weeks", "analog": "Mini-budget, Sep 2022 (GBP/USD to 1.03)",
     "story": "A UK fiscal shock sends gilt yields up and sterling down 12%. UK-focused stocks fall, "
              "but for a sterling investor everything priced abroad gains in GBP.",
     "market": -2,
     "sectors": {"Real Estate": -3, "Utilities": -2},
     "countries": {"United Kingdom": -10},
     "tags": {},
     "commodities": {},
     "fx": {"USD": 12, "EUR": 10, "CHF": 12, "JPY": 12, "EM": 8, "commodity_fx": 9}},
]

# ── Historical replays: today's holdings run through real market windows ─────
# Peak-to-trough dates of the global sell-off; prices come from Yahoo.
HISTORICAL_EPISODES = [
    {"key": "q4_2018", "name": "Q4 2018 Fed tightening", "start": "2018-09-20", "end": "2018-12-24"},
    {"key": "covid", "name": "COVID-19 crash", "start": "2020-02-19", "end": "2020-03-23"},
    {"key": "rates_2022", "name": "2022 inflation and rate shock", "start": "2022-01-03", "end": "2022-10-12"},
    {"key": "minibudget", "name": "UK mini-budget", "start": "2022-09-22", "end": "2022-09-28"},
    {"key": "yen_carry", "name": "Yen carry-trade unwind", "start": "2024-07-16", "end": "2024-08-05"},
    {"key": "deepseek", "name": "DeepSeek AI shock", "start": "2025-01-24", "end": "2025-01-27"},
    {"key": "tariffs_2025", "name": "2025 tariff shock", "start": "2025-02-19", "end": "2025-04-08"},
]


# ─────────────────────────────────────────────────────────────────────────────
# Static fundamentals estimates (FY2024e)
#
# Shown in grey in the exposure table where Yahoo has no live value, and the
# only source of ROIC. Keyed by company key. Values are display strings:
# [ticker, label, roe, fcf_margin, de, eps_growth, net_margin, roic, div_yield, beta, pe]
# ─────────────────────────────────────────────────────────────────────────────
COMPANY_ESTIMATES = {
  'alphabet':              ['GOOG','Big Tech','32.0%','23.0%','0.08x','+36.0%','19.0%','22.0%','0.5%','1.05×','~23×'],
  'amazon':                ['AMZN','Big Tech','21.0%','12.0%','0.65x','+95.0%','4.0%','13.0%','0%','1.20×','~45×'],
  'microsoft':             ['MSFT','Big Tech','35.0%','30.0%','0.30x','+20.0%','31.0%','28.0%','0.7%','0.95×','~33×'],
  'apple':                 ['AAPL','Big Tech','160.0%','26.0%','1.50x','+9.0%','23.0%','55.0%','0.4%','1.10×','~32×'],
  'netflix':               ['NFLX','Media','38.0%','18.0%','0.70x','+60.0%','13.0%','22.0%','0%','1.15×','~40×'],
  'mastercard':            ['MA','Payments','170.0%','45.0%','1.60x','+17.0%','42.0%','50.0%','0.5%','1.05×','~35×'],
  'eli lilly & co':        ['LLY','Pharma','55.0%','15.0%','1.80x','+100.0%','17.0%','25.0%','0.7%','0.40×','~60×'],
  'nvidia':                ['NVDA','Semis','90.0%','45.0%','0.20x','+120.0%','30.0%','70.0%','0.03%','1.70×','~40×'],
  'broadcom':              ['AVGO','Semis','28.0%','38.0%','1.00x','+30.0%','25.0%','20.0%','1.2%','1.20×','~35×'],
  'taiwan semicon mfg':    ['TSM','Semis','28.0%','30.0%','0.25x','+30.0%','35.0%','25.0%','1.5%','1.10×','~25×'],
  'asml holding':          ['ASML','Semis','50.0%','25.0%','0.40x','+25.0%','26.0%','35.0%','0.9%','1.30×','~35×'],
  'samsung electronics':   ['005930','Semis','9.0%','8.0%','0.05x','+40.0%','12.0%','9.0%','2.0%','1.00×','~14×'],
  'sk hynix':              ['000660','Semis','15.0%','10.0%','0.50x','+200.0%','10.0%','12.0%','1.0%','1.40×','~10×'],
  'tencent':               ['700','China Tech','18.0%','30.0%','0.30x','+30.0%','25.0%','15.0%','0.7%','0.90×','~18×'],
  'alibaba':               ['BABA','China Tech','10.0%','15.0%','0.20x','+10.0%','18.0%','8.0%','1.0%','0.85×','~14×'],
  'astrazeneca':           ['AZN','Pharma','17.0%','20.0%','0.60x','+15.0%','12.0%','12.0%','2.2%','0.50×','~18×'],
  'ferrari':               ['RACE','Luxury Auto','45.0%','20.0%','0.60x','+18.0%','19.0%','25.0%','0.6%','0.90×','~50×'],
  'rheinmetall':           ['RHM','Defence','25.0%','8.0%','0.40x','+50.0%','5.0%','15.0%','1.0%','1.30×','~45×'],
  'bae systems':           ['BA.','Defence','30.0%','9.0%','0.80x','+12.0%','7.0%','13.0%','2.5%','0.60×','~20×'],
  'adyen':                 ['ADYEN','Payments','25.0%','45.0%','0.00x','+25.0%','45.0%','25.0%','0%','1.30×','~45×'],
  'amd':                   ['AMD','Semis','5.0%','10.0%','0.05x','+25.0%','8.0%','5.0%','0%','1.60×','~45×'],
  'micron technology':     ['MU','Semis','12.0%','8.0%','0.30x','+100.0%','12.0%','10.0%','0.4%','1.50×','~15×'],
  'applied materials':     ['AMAT','Semis','40.0%','25.0%','0.35x','+10.0%','22.0%','30.0%','0.9%','1.40×','~22×'],
  'lam research':          ['LRCX','Semis','50.0%','28.0%','0.55x','+15.0%','26.0%','35.0%','1.0%','1.40×','~25×'],
  # ── Added to cover the top 100 holdings by exposure ─────────────────────
  'intel':                      ['INTC','Semis','—','—','—','—','—','2.0%','—','—','—'],
  'texas instruments':          ['TXN','Semis','—','—','—','—','—','18.0%','—','—','—'],
  'coca cola':                  ['KO','Consumer Staples','—','—','—','—','—','—','—','—','—'],
  'visa':                       ['V','Financials','—','—','—','—','—','—','—','—','—'],
  'bhp':                        ['BHP.AX','Mining','—','—','—','—','—','20.0%','—','—','—'],
  'nextera energy':             ['NEE','Utilities','—','—','—','—','—','6.0%','—','—','—'],
  'meta platforms':             ['META','Big Tech','—','—','—','—','—','25.0%','—','—','—'],
  'union pacific':              ['UNP','Rail','—','—','—','—','—','14.0%','—','—','—'],
  'enbridge':                   ['ENB','Midstream','—','—','—','—','—','6.0%','—','—','—'],
  'fortescue':                  ['FMG.AX','Mining','—','—','—','—','—','18.0%','—','—','—'],
  'samsung electro mechanics':  ['009150.KS','Semis','—','—','—','—','—','7.0%','—','—','—'],
  'tesla':                      ['TSLA','Auto/EV','—','—','—','—','—','9.0%','—','—','—'],
  'sk square':                  ['402340.KS','Holding Co','—','—','—','—','—','—','—','—','—'],
  'honda motor':                ['7267.T','Auto','—','—','—','—','—','6.0%','—','—','—'],
  'duke energy':                ['DUK','Utilities','—','—','—','—','—','5.0%','—','—','—'],
  'mediatek':                   ['2454.TW','Semis','—','—','—','—','—','20.0%','—','—','—'],
  'american tower':             ['AMT','REIT','—','—','—','—','—','8.0%','—','—','—'],
  'dbs':                        ['D05.SI','Banks','—','—','—','—','—','—','—','—','—'],
  'csx':                        ['CSX','Rail','—','—','—','—','—','12.0%','—','—','—'],
  'berkshire hathaway':         ['BRK-B','Conglomerate','—','—','—','—','—','8.0%','—','—','—'],
  'hyundai motor':              ['005380.KS','Auto','—','—','—','—','—','7.0%','—','—','—'],
  'national grid':              ['NG.L','Utilities','—','—','—','—','—','5.0%','—','—','—'],
}


# ─────────────────────────────────────────────────────────────────────────────
# Instrument symbols
#
# ETF ISINs identify a fund across brokers (IBKR may list CSPX as CSP1).
# Yahoo symbols mark each position to market and drive the price history; a
# position may also carry its own "yahoo" field, which wins over these maps.
# ─────────────────────────────────────────────────────────────────────────────

ISIN_MAP = {
    # All-World / Global
    "VWCE": "IE00BK5BQT80", "VWRL": "IE00B3RBWM25",
    # MSCI World
    "IWDA": "IE00B4L5Y983", "SWRD": "IE00BFY0GT14", "XDWD": "IE00BJ0KDQ92",
    # S&P 500
    "CSPX": "IE00B5BMR087", "CSP1": "IE00B5BMR087", "SXR8": "IE00B5BMR087",
    "VUSA": "IE00B3XXRP09", "VUAA": "IE00BFMXXD54", "IUSA": "IE0031442068",
    # Nasdaq-100
    "EQQQ": "IE0032077012", "CNDX": "IE00B53SZB19",
    # Emerging markets
    "EMIM": "IE00BKM4GZ66", "IS3N": "IE00BKM4GZ66", "VFEM": "IE0031786142",
    # Small cap
    "WSML": "IE00BF4RFH31",
    # Gold
    "IGLN": "IE00B8RFCH20", "SGLN": "IE00B4ND3602",
    # Factor, sector and regional funds in the demo
    "IAPD": "IE00B14X4T88", "IWFQ": "IE00BP3QZ601", "SMGB": "IE00BMC38736",
    "INFR": "IE00B1FZS467",
}

YAHOO_STOCK = {
    "700": "0700.HK",
    "GOOG": "GOOG",
    "AMZN": "AMZN",
    "MSFT": "MSFT",
    "LLY": "LLY",
    "AAPL": "AAPL",
    "RACE": "RACE",
    "RHM": "RHM.DE",
    "ADYEN": "ADYEN.AS",
    "AZN": "AZN.L",
    "BA.": "BA.L",
    "NVDA": "NVDA",
    "V": "V",
    "CSH2": "CSH2.L",
}
YAHOO_ETF = {
    "EMIM": "EMIM.L",
    "IAPD": "IAPD.L",
    "INFR": "INFR.L",
    "IWFQ": "IWFQ.L",
    "SGLN": "SGLN.L",
    "SMGB": "SMGB.L",
    "VUSA": "VUSA.L",
}
# ETFs whose "holdings" are commodities or bonds, not companies. Their
# constituent codes are futures symbols that collide badly with equity tickers
# ("CL" is crude oil here but Colgate-Palmolive on Yahoo), so they are never
# scored and never fetched.
NON_EQUITY_ETFS = {"SGLN"}

FX_PAIRS = {"USD": "USDGBP=X", "EUR": "EURGBP=X", "HKD": "HKDGBP=X",
            "CHF": "CHFGBP=X", "SEK": "SEKGBP=X", "DKK": "DKKGBP=X"}

# Company key -> Yahoo symbol for the companies scored on fundamentals and
# quality. ETF constituents with a ticker are added automatically (see
# market.scoring_universe); this curated list carries the exchange suffixes a
# constituent list often omits.
COMPANY_YAHOO = {
    "alphabet": "GOOG",
    "amazon": "AMZN",
    "microsoft": "MSFT",
    "apple": "AAPL",
    "netflix": "NFLX",
    "mastercard": "MA",
    "eli lilly & co": "LLY",
    "nvidia": "NVDA",
    "broadcom": "AVGO",
    "taiwan semicon mfg": "TSM",
    "asml holding": "ASML",
    "samsung electronics": "005930.KS",
    "sk hynix": "000660.KS",
    "tencent": "0700.HK",
    "alibaba": "BABA",
    "astrazeneca": "AZN.L",
    "ferrari": "RACE",
    "rheinmetall": "RHM.DE",
    "bae systems": "BA.L",
    "coca cola": "KO",
    "visa": "V",
    "adyen": "ADYEN.AS",
    "amd": "AMD",
    "micron technology": "MU",
    "applied materials": "AMAT",
    "lam research": "LRCX",
    # ── Added to cover the top 100 holdings by exposure ──────────────────────
    "intel": "INTC",
    "texas instruments": "TXN",
    "bhp": "BHP.AX",
    "nextera energy": "NEE",
    "meta platforms": "META",
    "union pacific": "UNP",
    "enbridge": "ENB",
    "fortescue": "FMG.AX",
    "samsung electro mechanics": "009150.KS",
    "tesla": "TSLA",
    "sk square": "402340.KS",
    "honda motor": "7267.T",
    "duke energy": "DUK",
    "mediatek": "2454.TW",
    "american tower": "AMT",
    "dbs": "D05.SI",
    "csx": "CSX",
    "berkshire hathaway": "BRK-B",
    "hyundai motor": "005380.KS",
    "national grid": "NG.L",
}


# ─────────────────────────────────────────────────────────────────────────────
# Private additions (.data/reference.json, git-ignored): symbols, profiles and
# estimates for holdings beyond the demo. See local.py.
# ─────────────────────────────────────────────────────────────────────────────
import local  # noqa: E402

local.merge("COMPANY_PROFILES", COMPANY_PROFILES, tuples=True)
for _name in ("COMPANY_ESTIMATES", "COMPANY_YAHOO", "YAHOO_STOCK", "YAHOO_ETF", "ISIN_MAP",
              "GICS_FROM_LABEL", "NON_EQUITY_ETFS", "CASH_TICKERS"):
    local.merge(_name, globals()[_name])
