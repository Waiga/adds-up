# Manifest

Every number published about this tool was produced against the exact material
described here. The point of the hashes is that you can obtain the same files
and check, and that when one of them changes you can tell.

Two corpora, because no single one exercises more than a fraction of the
checks. Both are named with what they can and cannot measure.

---

## Corpus 1 — published utility tariffs

**What it is for.** The volume-tier check, at scale. A utility tariff's rate
structure is a volume price list: buy up to *this* many units, pay *this* per
unit. Nothing else found in this work supplies tens of thousands of real
volume ladders.

**Source.**

```
https://apps.openei.org/USURDB/download/usurdb.csv.gz
```

The U.S. Utility Rate Database, maintained by the National Renewable Energy
Laboratory for the U.S. Department of Energy. No key, no account.

**Retrieved.** 9 September 2026. The server reported
`Last-Modified: Wed, 09 Sep 2026 08:43:34 GMT`.

**SHA-256.** `9005c5358de7e2471cef4216f475fbbc68afbe2f558dc1b24d7b00fc265d28d5`
(12,218,252 bytes, gzipped; 195,046,146 bytes uncompressed).

**Records in the export.** 58,920 rate records in 737 columns, from 2,938
utilities. Those four figures are printed by `tools/measure_corpus.py` under
`corpus.export`, counted from the file itself rather than from the price lists
derived from it — for a while a field named `records_in_export` held 18,049,
which is the number of *tariffs with a multi-tier rate structure*, and a
stranger re-running would have got a figure 3.3 times smaller than this
document's under the same name.

**Selection rule.** Every combination of record, rate structure and period
whose tier list holds **two or more tiers**. The three structures read are
`energyratestructure`, `demandratestructure` and `flatdemandstructure`, and
periods 0 to 5 of each. Nothing else is filtered, sorted or sampled.

That gives **29,521 price lists**, from **18,049 distinct tariffs** published
by **2,062 utilities**, holding **75,969 tier rows** in total. 12,324 of the
price lists come from a tariff with no end date, so are current.

58,387 of the 58,920 records carry a `source` field naming the utility's own
published rate schedule — a PDF or a tariff page — so a row can be traced back
to the document it was transcribed from.

**The reshape, and why it is the largest limitation of this corpus.** URDB
stores a tier table across up to 6 periods × 24 tiers of wide columns. The
measurement script writes each period's tiers out as rows, keeping URDB's own
field names: `tier`, `max`, `rate`, `adj`, `unit`. Values are copied
unmodified — nothing is corrected, rounded or reformatted.

But it means **every document in this corpus arrives with the same five column
names**, so the column-recognition step is exercised once rather than 29,521
times. Corpus 2 exists because of that.

**Reproduce it.**

```bash
curl -sO https://apps.openei.org/USURDB/download/usurdb.csv.gz
shasum -a 256 usurdb.csv.gz
python3 tools/measure_corpus.py usurdb.csv.gz
python3 tools/measure_corpus.py usurdb.csv.gz --samples audit.json
```

`tools/measure_corpus.py` prints every number published about this corpus as
JSON, including the export's own hash and the Python it ran on, so a result
carries its provenance. **32,996 of the 75,969 tier rows carry an adjuster**,
which is why the volume-tier check adds one to the rate before comparing;
that figure is `rows_with_an_adjustment` in the same output.

`--samples` draws the audit sample at seed 11, thirty findings, one per
tariff, so the same export gives anyone the same thirty rows.

**Licence.** OpenEI states that its content "is available under Creative
Commons Zero unless otherwise noted" (footer of
`https://openei.org/wiki/Utility_Rate_Database` and of the USURDB application,
read 9 September 2026). CC0 is a public-domain dedication, so unlike the
share-alike corpora used elsewhere in this portfolio it could be redistributed
here. It is not, because it is 195 MB and the URL above is stable; only the
measurements are published.

**What this corpus cannot measure.** It has no discount percentage, no list
price beside a net price, no stated bundle composition, no repeated item, no
currency column and no minimum-and-maximum pair. Six of the seven checks
cannot run against it at all, and the measurement records that as six
`DID NOT RUN` lines per document rather than as silence.

---

## Corpus 2 — US hospital standard-charges files

**What it is for.** Everything corpus 1 cannot reach:
`stated-discount`, `two-prices`, `inverted-range` and `unit-mismatch`. Also,
and just as importantly, **column recognition against headers this project did
not write**, several hundred of them, from files authored independently by
different hospitals and different vendors.

**Collected.** 9 September 2026.

**No single checksum, and why.** There is no one file to hash: the corpus is
200 documents fetched from 200 hospital websites.

[`docs/hospital-corpus.csv`](hospital-corpus.csv) is the citation list, and it
is the one thing from this corpus that *is* committed here. 200 rows, 48 kB:
the CMS certification number, the state, the facility name, the exact URL, the
size of the CSV as analysed, the size as downloaded, and the **SHA-256 of each
CSV**. Those 200 hashes are the checksum for this corpus. 199 of the numbers
are distinct — one appears twice, for two locations of one certified provider.

**It is a bibliography, and deliberately nothing more.** It carries no price,
no charge, no row of any hospital's file, and no personal data of any kind:
every field in it is a public federal identifier, a facility name, or a URL
that 45 CFR 180.50 requires to be published and downloadable. The files
themselves are not redistributed here. That is the same choice made for the
tariff corpus and for the transit feeds — cite the source, publish the
measurement, leave the documents where their publishers put them.

You very likely do not have the same files: hospitals republish these
continuously, and a hash that no longer matches means the document has moved
on, not that anything is wrong.

**Why these files exist.** 45 CFR 180.50 requires every hospital in the United
States to publish a machine-readable file of its standard charges, "free of
charge", "without having to establish a user account or password", and
accessible "to automated searches and direct file downloads". The CMS template
gives them a common shape: a gross charge, a discounted cash price, a
payer-specific negotiated dollar amount, a negotiated percentage *of* the
gross charge, and a declared minimum and maximum.

**Index.** CMS publishes no list of the files themselves. The URLs come from

```
https://raw.githubusercontent.com/nathansutton/hospital-price-transparency/main/dim/urls/{state}.json
```

51 JSON files, one per state plus DC, **5,023 rows**, each carrying a CCN, a
hospital name and a direct `file_url`. Retrieved 9 September 2026. That index
is a third-party project (Apache-2.0), not a government publication, and it is
**not current**: it was last refreshed in January 2026.

Of the 865 index rows the collection actually reached, **260 — 30% — did not
answer a `HEAD` request at all**. That counter counts any failure: a timeout
and a TLS error along with a genuine 404. Collection stops at the target
count, so only a sixth of the 5,023 rows were ever tried, and 30% is a rate
over what was tried rather than over the index.

**Selection rule.** The 5,023 rows are shuffled at seed 11 and worked through
in that order. A row is kept when all of the following hold:

1. a `HEAD` request returns a status and a non-zero `Content-Length`;
2. that length is **under 40 MB** — this is the size of the *download*, and
   many hospitals publish a zip, so a file that passes the cap at 2.7 MB can
   unpack to 83 MB of CSV. The largest file in the collected corpus is
   **1,083 MB** of CSV from a download well under the cap;
3. the body downloads, and if it is a zip, it contains a `.csv`;
4. the first 16 kB of that CSV contains the string `standard_charge`, which is
   how a current CMS-template file is told from a pre-2022 chargemaster with a
   five-column layout of its own.

Collection stops at the target count. Everything rejected is counted by
reason, in `_index.json`. For the 200 files these numbers come from, the
counts were: 5,023 index rows, of which 865 were reached before the target was
met — 605 answered a `HEAD`, 260 did not; of the 605, 226 were over the cap and
106 declared no length; 53 downloaded but were not CMS-template files, 1
download failed, and 200 were kept.

The file is named `<n>-<ccn>-<basename>.csv` whatever the URL called it. An
earlier version took the extension from the URL, so 38 of 200 files were named
`.aspx`, `.php`, `.json`, `.CSV` or nothing at all — and the measurement
matched `*.csv` and silently measured 162 of them.

**What is not measured about the bias.** Nothing in `_index.json` records a
bed count, a facility type or system membership, and no script compares the
kept set against the rejected one. The paragraph below is a mechanism, argued
from the selection rule, not a measurement. It is written as an argument
because that is what it is.

**The bias this creates, stated plainly.** The 40 MB cap is not neutral. Real
standard-charges files run to hundreds of megabytes, and a hospital that
publishes an uncompressed file is more likely to be excluded than one that
zips the same content. The corpus therefore over-represents smaller hospitals
— behavioural health units, critical-access hospitals, single-site facilities
— with shorter chargemasters and fewer payer contracts, and it
under-represents any large system that publishes raw CSV.

It does not exclude large files altogether: the zip exception lets several
hundred-megabyte documents through. The 200 files collected hold **9.28 GB of
CSV** — a median of **6.89 MB**, a maximum of **1,083 MB** — from downloads
whose median was **5.87 MB**. That spread is useful, and it is what produced
the tool's memory and timing numbers, but it fell out of the rule rather than
being what the rule was designed to give. Every one of those figures is in
`_index.json`, which records both the CSV size and the downloaded size for
each file.

The cap was chosen so the corpus could be collected and re-collected in under
an hour, and it is why this corpus is a few hundred documents rather than
several thousand.

**Reproduce it.**

```bash
python3 tools/fetch_hospital.py corpus/ --count 200 --cap-mb 40
python3 tools/measure_hospital.py corpus/
python3 tools/measure_hospital.py corpus/ --samples audit.json
```

`corpus/_index.json` records, for every file kept: the CCN, the state, the
hospital name, the exact URL, the byte count and the SHA-256 of the CSV as
analysed. That file is the manifest for this corpus, and it is written by the
fetch rather than by hand.

**These files are republished constantly.** A hospital may update its file any
day, and the CMS template itself has moved from v2.0 through v2.2 to v3.0.
The per-file hashes in `_index.json` are how you tell whether you have the
same documents these numbers came from. You very likely do not, and should
expect the counts to move.

**Licence.** These are documents a federal regulation requires to be published
free and downloadable. CMS asserts no terms on them and the files carry no
copyright notice. The index used to find them is Apache-2.0. **No file from
this corpus is redistributed in this repository**: only the measurements, and
the URLs and hashes needed to obtain the same files.

**No patient data.** These files describe prices for procedures, not people.
Before any of this was published the corpus was scanned for personal data;
what it contains is facility-level information only — hospital name, address,
NPI, the name of the person attesting to the file. Nothing from any hospital
file is quoted in this repository beyond column names and a handful of prices.

**What this corpus cannot measure.** It has no quantity or volume band, so
`volume-tier` and `discount-tier` cannot run against it. It states no bundle
composition, so `bundle-above-parts` cannot either. Between the two corpora,
**`bundle-above-parts` is measured by nothing at all**, and the README says so
rather than implying otherwise.

---

## Where else was looked, and what was there

Two corpora is not a design preference. It is what a survey of the obvious
alternatives produced, and the survey is recorded because "we looked" is worth
something and because the next person should not have to repeat it.

### Open government data portals

Searched on 9 September 2026, through each portal's own API, for *price list*,
*fee schedule*, *rate schedule*, *tariff*, *price schedule*, *fees and
charges*, *unit price*, *pricing* and *charges*, plus the equivalents in
Polish, French, Italian, Dutch, German and Slovak.

| portal | working API form |
|---|---|
| data.gov | `https://catalog.data.gov/search?q=…` with `Accept: application/json` — **the CKAN API at `/api/3/action/*` is gone**, every action 404s |
| data.gov.uk | `https://ckan.publishing.service.gov.uk/api/3/action/package_search` (the `data.gov.uk` path 301s here) |
| open.canada.ca | `https://open.canada.ca/data/api/3/action/package_search` |
| data.gov.au | `https://data.gov.au/data/api/3/action/package_search` |
| Socrata | `http://api.us.socrata.com/api/catalog/v1?q=…` |
| data.europa.eu | `https://data.europa.eu/api/hub/search/search?q=…` |
| GSA CALC | **gone** — `calc.gsa.gov/api/rates/` 404s, `api.calc.gsa.gov` does not resolve, and `buy.gsa.gov` is behind single sign-on. There is no public contract labour-rate API today. |

**These figures came from a one-off reconnaissance and no script in `tools/`
reproduces them.** That is a deliberate exception to this repository's rule
that every published number has a producing script, and it is flagged here
rather than glossed: the survey was a search of six portals whose APIs differ,
whose result sets are capped by relevance, and which change; scripting it
would produce a number that drifts without meaning anything. The API forms
above are given so the search can be repeated by hand, and the conclusion —
that these portals do not hold 500 independent price lists — is what the
figures are for.

Twelve terms across six portals gave **3,802 unique CSV or XLSX download
URLs**. Of those, **43** have a title that names a price list or a fee
schedule. A random sample of 180 was downloaded and its headers read: 25 could
not be fetched, and of the 54 that parsed as CSV, **three** were genuinely
price lists — **a true-positive rate of about 1.7% for naive keyword
harvesting**.

The word does not mean the thing. *Tariff* returns surveys about the business
impact of tariffs and feed-in-tariff capacity statistics. *Charges* returns
electric vehicle charge points and penalty charge notices. A dozen files with
a "Total Charges" column turned out to be hospital discharge records and
inmate release logs.

What is genuinely there, and is genuinely good, is concentrated and
non-independent: Polish law obliges housing developers to publish a
standardised apartment price list as open data, and 33 such titles republish
near-daily, giving 1,908 dated snapshots of the same few dozen documents.
Italian regional public-works price books, French transit tariffs and Canadian
municipal fee schedules make up most of the rest.

**So: 500+ price-list *files* can be assembled from data.europa.eu alone. 500
price lists from 500 independent publishers cannot.** Four genuine ones were
checked against this tool's own class of question and behaved exactly as it
would want — a Campania public-works price book in which base price plus
overheads plus profit equals the final price in 12,708 of 12,708 parseable
rows, and a Polish developer price list in which area times price per square
metre equals the price in 99 of 99, but only against the correct one of its
two area columns.

**One of them is a warning this tool took to heart.** A Czech integrated
transport fare list shows 2,396 apparent "price falls as distance rises"
violations when rows are grouped by tariff and distance alone, and **zero**
once `validity_days` is part of the group. An under-specified group key does
not produce a few wrong findings; it produces thousands. That is why
`two-prices`, `unit-mismatch` and the tier checks hold every recognised
qualifier column equal, and why the limitations document names an unrecognised
qualifier as the most likely cause of a wrong finding on your file.

### A corpus that was collected and then rejected

**GTFS fare tables**, from the Mobility Database catalogue. Published transit
fares are real price data, free and machine-readable, spread across many
currencies — which made this look like the one available source that could
exercise `unit-mismatch` on a currency rather than on a unit.

**Source.**

```
https://bit.ly/catalogs-csv
    -> https://storage.googleapis.com/storage/v1/b/mdb-csv/o/sources.csv?alt=media
```

The short link is what the Mobility Database publishes; the target above is
where it redirects, and is what a script actually fetches.

**Retrieved.** 9 September 2026. The catalogue served
`Last-Modified: Mon, 31 Aug 2026 17:54:03 GMT`.

**No checksum is published here, deliberately.** The catalogue carries an
`ETag` but no stable hash, each feed is re-published by its own agency on its
own schedule, and `urls.latest` points at a mirror that is refreshed
continuously. Any hash taken today would fail tomorrow and prove nothing. What
is stable is the *structural* fact this corpus was rejected for, which does
not depend on which day the feeds were fetched.

**Counts, from the catalogue as retrieved.** 1,977 GTFS static feeds, not
counting redirected entries, across 87 countries.

**Licence.** Mixed, and mostly absent: of the 1,977 feeds, **1,183 state no
licence at all** in the catalogue. The rest point at their own agency's terms
— Spain's national access point (111), Trafiklab (57), the UK Open Government
Licence (38), BC Transit (31), Estonia's ministry (23) and a long tail. No
feed is redistributed here and none was kept; the probe reads each one in
memory and discards it.

`tools/probe_gtfs.py` is the script that established this and prints every
figure below:

```bash
python3 tools/probe_gtfs.py --feeds 140
```

The reason the corpus fails is structural, and it is worth recording:

| | |
|---|---|
| feeds tried, at seed 11, until 140 held a fare table | 345 |
| — unreachable | 65 |
| **feeds with a `fare_attributes.txt`** | **140** |
| fare rows in them | 1,174,347 |
| distinct currencies across those feeds | 12 |
| feeds with a repeated `fare_id` | **0** |
| feeds carrying more than one currency | **0** |
| feeds using the GTFS-Fares v2 `fare_products.txt` | 8 |

Twelve currencies appear across the sample — USD, EUR, CAD, JPY, BRL, PEN,
INR, CDF, MDL, RWF, RON, RSD — and **never two of them in one feed**, which is
the whole of the problem.

`fare_id` is a primary key in the GTFS specification, so the same fare can
never appear twice, and a feed is published by one agency in one currency. The
two checks this corpus was collected for **cannot fire on it even in
principle**. It has no volume band, no discount and no minimum-and-maximum
pair either.

It is recorded here because "we looked at transit fares" is worth knowing, and
because a corpus that cannot fire a check is a more useful thing to publish
than a corpus that fires it by accident.

---

## The hand audits

Findings were read by hand against the file they came from. Each sample is
reproducible from the corpus above.

| Check | Corpus | Sample | What was read |
|---|---|---|---|
| volume-tier | tariffs | 30 findings, seed 11, one per tariff | the tier table's own printed rates and adjusters |
| stated-discount | hospitals | 30 findings, seed 11, one per file | the gross, percentage and dollar printed on that row |
| two-prices | hospitals | 30 findings, seed 11, one per file | the two rows, and every column that might tell them apart |
| inverted-range | hospitals | 30 findings, seed 11, one per file | the row's own printed minimum and maximum |
| unit-mismatch | hospitals | 30 findings, seed 11, one per file | the rows, and the unit printed on each |
| discount-tier | — | — | **no corpus exercises it** |
| bundle-above-parts | — | — | **no corpus exercises it** |

Redraw any of them with:

```bash
python3 tools/measure_corpus.py usurdb.csv.gz --samples audit.json
python3 tools/measure_hospital.py corpus/ --samples hospital-audit.json
```

The draw is deduplicated by document and seeded at 11, so the same corpus
gives the same findings. A different corpus will not.

**The hospital audits are mechanically aided, and the aid is published.**
`tools/audit_hospital.py` goes back to the rows a finding names, re-reads them
with `csv.reader`, and prints every column in which the two rows differ:

```bash
python3 tools/audit_hospital.py corpus/ hospital-audit.json
```

For the two checks that state a *pair* of rows, it sorts each finding into
`agree` — the two rows hold the same value in every column the tool could read
— `derived`, where they differ only in figures computed from the price itself,
and `distinguished`, where a column the tool has no name for holds different
values and the document may well be separating the two rows.

For the two that state a *single* row, it goes back to that row and confirms
the values the finding quotes are cells in it. That is not the computation the
check performed; it is the question a reader of the audit is asking, which is
whether the finding describes the document.

**Only the first of those is a verdict the script can give.** Whether a
difference *matters* is the judgement, and it is made by a person looking at
what the script prints. That is what caught the ten findings in the first
audit whose two rows were identical but for a note reading `Gross Charge Type:
Sta` against `Gross Charge Type: Fee` — the script reported the difference; a
person decided it was a real one.
