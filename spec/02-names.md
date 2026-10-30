# 02 · Company names (`names.py`, `normalizeName`/`companyKey` in `static/app.js`)

## Purpose

The same company arrives under many spellings: the broker's "ALPHABET INC-CL C",
one ETF's "Alphabet Inc A", another's "Alphabet Inc C", or "Samsung Electronics
Co., Ltd.". This module defines three functions:

- **`canonical_company_name(description, isin=None)`** gives a short display
  name, for broker imports.
- **`display_name(name, isin=None)`** is the same, but for ETF holdings. It keeps
  bond names and duplicate-line counters.
- **`company_key(name)`** gives the **identity** used for every per-company
  lookup: merging rows, fundamentals, quality, profiles and estimates.

`normalize_name` and `company_key` exist **twice**: in Python, which keys the
fundamentals and quality documents, and in JS, which keys the browser's lookups.
The two implementations must give identical output. `NAME_ALIASES` and
`COMMODITY_SECTORS` are defined once in Python and served to the browser.

## `canonical_company_name(description, isin)`

1. If `isin` is in `COMPANY_NAME_BY_ISIN`, return that override.
2. Remove noise markers, case-insensitively:
   - "/THE" at the end;
   - "-SPON ADR…" and the like;
   - "-CL C" or "-CLASS A…";
   - a trailing "-H" or "-A";
   - the standalone words SPONSORED, ADR, ADS, CLASS X and SHARES.
3. Remove legal forms: INC, CORP, PLC, NV, BV, SE, SPA, SAS, ASA, OYJ, KGAA,
   LTD, LIMITED, LLC, PTE, CO, COMPANY, HOLDING(S), GROUP and SAB DE CV.
4. Collapse whitespace, and trim trailing `, & / -`. If the result is empty,
   return the original description.
5. Fix the case of each word:
   - words in `_ACRONYMS` (AI, BAE, SAP, …) stay upper-case;
   - other all-caps words of 3 letters or fewer stay as they are;
   - other all-caps words are title-cased one hyphen-part at a time;
   - mixed-case words are left alone.

## `display_name(name)`

- Bond lines (anything matching `\d+\.\d+\s*%`) are returned unchanged.
- A trailing counter such as "(2)" is kept. It marks a genuinely separate line,
  for example preferred versus common shares.
- Otherwise the result is `canonical_company_name(name)`, falling back to the
  input if that comes back empty.

## `normalize_name(n)`

This is an exact port of the JS function `normalizeName`. Apply the steps in
order:

1. If `n` is a bond (it matches `\d+\.\d+%`), return `n.lower()`.
2. Detect a trailing share class with `\s+(?:cl(?:ass)?\s+)?([A-C](?:/[A-C])?)$`
   (case-insensitive). Remember it as `" " + CLASS.upper()` and cut it off.
3. Lower-case, then fold accents (NFD, dropping combining marks).
4. Remove `.com` at the end of a word.
5. Remove parentheticals, except numeric counters: `\s*\((?!\s*\d+\s*\))[^)]*\)`.
6. Delete dots. Replace commas and hyphens with spaces.
7. Remove these legal-form tokens as whole words:
   `corp corporation inc incorporated ltd limited plc co company ag nv bv sa se
   spa sas ab asa oyj kgaa pte llc lp publ ser holdings holding group adr ads com`.
8. Collapse whitespace and trim. Strip trailing `[\s&.,;:_\-]+`.
9. Apply `NAME_ALIASES` (for example "advanced micro devices" → "amd", and
   "tsmc" → "taiwan semicon mfg"), then re-append the class suffix.

## `company_key(n)`

`company_key(n)` is `normalize_name(n)` with two more steps:
- remove a trailing numeric counter, `\s*\(\s*\d+\s*\)\s*$`;
- remove a trailing class letter, `\s+[A-C](/[A-C])?$`.

So "Alphabet Inc A" and "Alphabet Inc C" both become `alphabet`, and the
"Samsung … (2)" preferred line merges with the common shares.

## Worked examples

| Input | `canonical_company_name` | `company_key` |
|---|---|---|
| `Samsung Electronics Co., Ltd.` | Samsung Electronics | samsung electronics |
| `Samsung Electronics Co Ltd (2)` | Samsung Electronics (2) | samsung electronics |
| `Gold (Physical)` | Gold (Physical) | gold |
| `L'Oréal SA` | L'Oréal SA | l'oreal |
| `Amazon.com Inc` | Amazon.com | amazon |
| `Advanced Micro Devices Inc` | Advanced Micro Devices | amd |
| `US TREASURY 3.15% 2031` | US Treasury 3.15% 2031 | us treasury 3.15% 2031 |
| `Microsoft Corp` | Microsoft | microsoft |
| `ALPHABET INC-CL C` | Alphabet | alphabet cl |

The last row shows a known quirk: a hyphenated class suffix is not stripped by
`normalize_name`. Broker names are therefore passed through
`canonical_company_name` **before** they are stored, which is what makes the
key `alphabet`.

## Commodities

`COMMODITY_SECTORS` maps a commodity line's company key to a commodity type.
For example "gold" and "silver" map to Precious Metals, "wti crude oil" to Oil &
Gas, "corn" to Agriculture, and "live cattle" to Livestock.
`commodity_sector(name)` looks up `COMMODITY_SECTORS[company_key(name)]`.

## Acceptance checks

1. The worked-example table holds in Python. The JS `companyKey` gives the
   same keys for the same inputs.
2. `company_key("Alphabet Inc A") == company_key("Alphabet Inc C") == "alphabet"`.
3. `display_name("Samsung Electronics Co Ltd (2)")` keeps "(2)".
