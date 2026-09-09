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
utilities.

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
JSON, including the export's own hash, so a result carries its provenance.

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
**not current**: it was last refreshed in January 2026, which is the main
reason a third of its URLs no longer resolve.

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
reason, and those counts are published beside the results.

**The bias this creates, stated plainly.** The 40 MB cap is not neutral. Real
standard-charges files run to hundreds of megabytes, and a hospital that
publishes an uncompressed file is more likely to be excluded than one that
zips the same content. The corpus therefore over-represents smaller hospitals
— behavioural health units, critical-access hospitals, single-site facilities
— with shorter chargemasters and fewer payer contracts, and it
under-represents any large system that publishes raw CSV.

It does not exclude large files altogether: the zip exception lets several
hundred-megabyte documents through, and the corpus spans 8.6 GB of CSV with a
median of 5.9 MB and a maximum of 1,083 MB. That spread is useful — it is what
produced the tool's memory and timing numbers — but it is a spread that fell
out of the rule rather than one the rule was designed to give.

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

**GTFS fare tables**, from the Mobility Database catalogue
(`https://bit.ly/catalogs-csv`, 1,977 static feeds in 87 countries with stable
mirrored download URLs). Published transit fares are real price data, they are
free and machine-readable, and they span many currencies, which looked like
the one available source that could exercise `unit-mismatch` on currency
rather than on units.

139 feeds were collected and measured before the idea was abandoned. The
reason it fails is structural, and it is worth recording:

| | |
|---|---|
| feeds with a `fare_attributes.txt` | 139 |
| fare rows in them | 1,174,346 |
| feeds with a repeated `fare_id` | **0** |
| feeds carrying more than one currency | **0** |

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
python3 tools/measure_hospital.py corpus/ --samples audit.json
```

The draw is deduplicated by document and seeded at 11, so the same corpus
gives the same findings. A different corpus will not.
