# adds-up

Reads a price list and reports the arithmetic in it that contradicts itself.

Runs entirely on your machine. No account, no API key, no upload, no network
call, no dependencies beyond Python itself.

```
$ adds-up examples/volume-tiers.csv

6 row(s) under a header read from row 4, the last header-shaped row above the data; 3 row(s) above it were read as a title block.
5 of 5 column(s) were given a role.
3 of 7 check(s) ran, comparing 4 pair(s) of numbers. 1 finding(s).

VOLUME-TIER
  a larger quantity priced higher than a smaller one, in the price column named

  'W-100' has a Unit price of 11.80 at Quantity 250, and 11.20 at Quantity 50
      row 6: Quantity 50, Unit price 11.20
      row 7: Quantity 250, Unit price 11.80
      at volume-tiers.csv!row 6, Unit price, volume-tiers.csv!row 7, Unit price

CHECKS
  ran      volume-tier          1 finding(s) from 4 comparison(s) — read 'Quantity' against 'Unit price'
  DID NOT RUN discount-tier     no column names a discount percentage
  DID NOT RUN bundle-above-parts no column names the items a bundle is made of, so no composition is stated in this document
  DID NOT RUN stated-discount   no column names a list price
  ran      two-prices           0 finding(s) from 0 comparison(s) — read 'SKU' against 'Unit price', holding 3 other column(s) equal
  DID NOT RUN inverted-range    no column names the bottom of a range
  ran      unit-mismatch        0 finding(s) — read 'Currency' against 'SKU', holding 2 other column(s) equal (compares text, not numbers)

  A check that did not run has found nothing because it was not made.

COLUMNS
  'SKU'                              item               'sku' is a known name for item
  'Description'                      item               'description' is a known name for item
  'Quantity'                         quantity           'quantity' is a known name for quantity
                                                        numbers: no cell in this column carries a separator
  'Unit price'                       unit_price         'unit price' is a known name for unit_price
                                                        numbers: 6 cell(s) in this column can only be read as 1,234.56
  'Currency'                         currency           'currency' is a known name for currency
```

## The thing to understand before anything else

**A price list does not state a cost.**

That one sentence decides everything this tool is. Almost every question a
person wants to ask about a price list — is this profitable, is it
competitive, is the discount too generous, should tier 3 be cheaper — needs at
least one number the document does not contain.

So this tool answers none of them, and it is built so that it cannot look as
though it might. There is no margin here, no benchmark, no score, no severity,
no recommendation. **It will never tell you a price is right, wrong, high,
low, fair or profitable.**

What is left is the set of statements a document makes that cannot all be true
at once. *"Tier 3 costs more per unit than tier 2"* is a finding. *"Your
pricing is wrong"* is not, and never will be.

## The second thing: a finding is not a defect

The tool reports that two numbers in a document cannot both describe one
consistent price. It does not know which is wrong, or whether either is.

The corpus proved this the hard way. **Inclining block pricing — charging more
per unit as you use more — is deliberate and everywhere in utility tariffs.**
Of thirty volume-tier findings read by hand against 29,521 published tariffs,
all thirty were arithmetically correct and **none of the thirty was a
mistake**: every one was pricing somebody meant to set. The check says a
larger band is priced higher, in those words, and stops.

## Install

```bash
pip install .
```

Python 3.11 or newer. Nothing else.

## Use

```bash
adds-up prices.csv
adds-up prices.xlsx --sheet "Trade rates"
adds-up prices.csv --format markdown       # to paste into an email
adds-up prices.csv --format json           # for a pipeline
adds-up prices.csv --skip volume-tier
adds-up prices.csv --header-row 3          # the header is not where it looks
adds-up prices.csv --map 3=unit_price --map 'Band C'=quantity
adds-up --list-checks
adds-up --list-columns                     # every column name it recognises
```

Exit codes: `0` nothing found, `1` at least one finding, `2` could not run.

**Exit 0 requires that two numbers were actually compared.** A file that did
not parse exits `2`, and so does a run in which nothing was compared — every
check switched off, no check able to find its columns, or the columns it found
empty. The report prints the comparison count, so "3 checks ran" and "3 checks
ran and compared nothing" are never the same line.

That gate is on comparisons rather than on whether a check reported that it
ran, and the difference is not theoretical: an adversarial review found a
price list with a real inverted tier in it exiting `0` because its price
column had a heading the vocabulary did not know, and `unit-mismatch` — which
needs no numbers at all — had run and found the units consistent. A green
result over a price list nothing was compared in is the one outcome this tool
exists not to produce.

## The seven checks

Each can be switched off on its own, and the report always prints which ran
and which did not, with a reason.

| | |
|---|---|
| **volume-tier** | A larger quantity is priced higher than a smaller one, in the price column named. If an adjustment column is present it is added to the rate first. |
| **discount-tier** | A larger quantity is given a smaller discount percentage than a smaller one. |
| **bundle-above-parts** | A row names the items it contains, this document also prices every one of them, and the bundle costs more than their sum. If a component is not priced here, the total is *not established* and the row is set aside, not reported. |
| **stated-discount** | A percentage printed beside a list price and a net price does not produce the second from the first, allowing for the precision the document itself prints. |
| **two-prices** | The same item is priced twice, differently, and no other column tells the rows apart. |
| **inverted-range** | A row states a minimum above its own maximum. |
| **unit-mismatch** | One item is priced in two different units, or two different currencies. A document that spans several currencies is normal and is not reported. |

**Every one of these is arithmetic on numbers printed in the input.** None
uses a cost, a margin, a benchmark, a market rate or a currency conversion,
because a price list states none of those.

### Two narrowings that cost coverage on purpose

**A percentage has two opposite meanings, and only its name decides which.**
*20% off* and *pays 20% of* are contradictory instructions and both appear in
real price lists — the second is how the US hospital price-transparency schema
states a negotiated rate. So there are two roles, and the column's name picks
one. Trying both readings and reporting only when neither fits was rejected:
a check that accepts whichever reading happens to fit can never fail.

**An undecidable number is refused, not guessed.** `1,234` is 1234 in one
convention and 1.234 in the other. The convention is decided once per column
from the cells that are unambiguous, and a column with none is refused — the
checks that needed it do not run, and the report says so. On the tariff corpus
that costs 316 of 29,521 documents — rate sheets in which the only cells
carrying a separator are of that undecidable shape, so nothing in the column
settles it.

## How it decides what a column is

A price list has no schema, so the tool reads the word at the top of each
column and looks it up. **Roles come from names, never from the shape of the
contents** — a column of numbers between 0 and 100 is equally likely to be a
discount, a case pack, a quantity break or a stock figure, and picking one on
that evidence is how a tool invents a contradiction.

`adds-up --list-columns` prints the whole vocabulary, because a vocabulary you
cannot read is indistinguishable from a guess. A name it does not know gets no
role, the checks that needed it do not run, and the report names the word it
was looking for. `--map` settles anything it got wrong.

One ambiguity cannot be settled by the name at all: a column called `max` is
the top of a volume band in a tier table and the top of a price range in a
rate sheet. The rule is that a bound is a range end only when a column naming
the other end is present, and a quantity otherwise — and the report prints
which reading it took.

## Format scope

**CSV, TSV and XLSX. Not PDF.** A PDF price list is a page of positioned
glyphs, and rebuilding rows and columns from it is a separate problem with its
own error rate; every finding would then carry two uncertainties with no way
to tell them apart. The tool says it does not read PDFs rather than reading
them badly.

The `.xlsx` reader is `zipfile` and `xml.etree` and nothing else, including
the number formats — because a cell storing `42.50425` and displaying `42.50`
must set the tolerance from what it *displays*, or the discount check is wrong
on every formatted workbook.

### It does not collide with `show-your-work`

Both read spreadsheets; they ask opposite questions.
[`show-your-work`](https://github.com/Waiga/show-your-work) asks **how the
workbook was built** — a formula someone typed over, a `SUM` that stops a row
short, a hidden sheet, a stale link. It needs formulas.

`adds-up` never looks at a formula. It reads values as printed and asks
whether the pricing they state is self-consistent, which is why it works on a
CSV that has no formulas at all. A workbook can be perfectly built and price
tier 3 above tier 2; a workbook can have a broken `SUM` and price everything
consistently. Run both.

## Measured against real price lists

Unit tests pass on the inputs their author imagined, which proves very little.
This was run over two corpora of real published documents, neither written by
this project. Full provenance, hashes and selection rules:
[`docs/corpus-manifest.md`](docs/corpus-manifest.md).

`tools/measure_corpus.py` and `tools/measure_hospital.py` are the scripts that
produced every number below.

### Corpus 1 — 29,521 published utility tariffs

The OpenEI U.S. Utility Rate Database, retrieved 9 September 2026, SHA-256
`9005c535…d28d5`. Every rate structure with two or more tiers, from 18,049
distinct tariffs published by 2,062 utilities.

| | |
|---|---|
| Price lists | 29,521 |
| Tier rows in them | 75,969 |
| Crashes | **0** |
| `volume-tier` ran on | 29,205 |
| — did not run, rate column undecidable | 316 |
| **`volume-tier` findings** | **15,487 on 12,050 documents** |
| — where the smaller band is priced at zero | 4,404 |

**Accuracy: 30 of 30 correct.** Thirty findings drawn at seed 11, one per
tariff, each read against that tariff's own printed tier table. Every one
quotes the two rates the file prints, in the right order. None was wrong.

**A stronger check than the sample.** The measurement script classifies each
tier ladder's direction independently of the tool — rising, falling, mixed or
flat — straight from the raw export. The two agree almost exactly:

| ladder shape | tariffs | documents with a finding |
|---|---|---|
| falling (an ordinary volume discount) | 16,954 | **0** |
| flat | 515 | **0** |
| rising | 10,711 | 10,709 |
| mixed (falls, then rises) | 1,341 | 1,341 |

The 316 documents whose rate column was refused break down as 313 falling, 2
rising and 1 flat — which accounts for the two rising ladders with no finding
exactly. **Nothing falling or flat was reported anywhere in the corpus.**

**And 29 of the 30 are also not mistakes.** This is the number that matters
and it is not a flattering one:

- **11 of 30 have a first band priced at zero** — an allowance included in a
  fixed charge, or the threshold above which a demand charge starts. That is
  not an inverted tier in any useful sense. The tool prints a note on these;
  across the whole corpus they are 4,404 of the 15,487 findings, **28%**.
- **18 of 30 are inclining block tariffs**, which are conservation pricing and
  entirely intentional. 6,254 of the 10,020 residential rate structures in
  this corpus produce a finding, against 4,726 of 14,565 commercial ones.
- **1 of 30 looks like a data defect** rather than a pricing choice: a
  seven-tier industrial ladder whose thresholds run 3,000 / 10,000 / 200,000 /
  200 / 400 / 600, which is two rate blocks concatenated into one.

So on this corpus the check is **100% arithmetically right and about 3%
useful**. Both halves of that are worth publishing.

**So this corpus establishes that the check's arithmetic is right at scale,
and establishes nothing whatever about how often an inverted tier is a
mistake.** A utility tariff is the wrong document to ask that of. Said here
rather than left for a reader to assume the reverse.

### Corpus 2 — US hospital standard-charges files

Files every US hospital is required to publish under 45 CFR 180.50, in the CMS
template's CSV shape, collected 9 September 2026. This corpus exists because
the tariff corpus exercises exactly one of the seven checks, and because it is
the only source found where **several hundred column headers were written by
people who have never heard of this tool**.

<!--MEASUREMENT-->

## What the measurement found that the tests did not

Every one of these was a real defect, found only by meeting real published
files. The suite was green throughout.

- **`0.091` was refused as an undecidable separator.** The rule about `1,234`
  had never met a price below one unit. 1,898 real tariffs were refused
  because of it. A leading zero cannot be a thousands group, and now says so.
- **A percentage was compared against the wrong price column.** In the CMS
  schema, `standard_charge|negotiated_percentage` belongs with
  `standard_charge|negotiated_dollar`, and `standard_charge|discounted_cash`
  sits beside them sharing the same prefix. Pairing on the family alone chose
  the cash price and produced **363,426 findings across ten files**, every one
  a comparison between two numbers never meant to agree. Columns are now
  paired by the longest run of shared leading words.
- **Two rows with the same description and different codes were reported as
  one item priced twice.** Holding only the first item column equal produced
  **75,968 findings across 22 files**. Every column naming what is priced is
  now part of the identity, and `code|1`, `code|2` are recognised as such.
- **`unit-mismatch` reported every multi-currency price list.** It ignored the
  qualifier columns — region, plan, payer — that legitimately separate the
  rows. A price list quoting one product in GBP for the UK and EUR for the EU
  is a normal document.
- **One unusable column aborted an entire check.** A wide file can carry
  hundreds of payer blocks, and one empty percentage column stopped the other
  hundreds from being read at all.
- **"could not be read" was printed for a column that simply held no number.**
  Those are different facts about a document, and the report now says which.
- **A malformed `.xlsx` raised a `KeyError` out of `zipfile`** instead of the
  message saying what the tool reads.
- **The volume-tier finding said "per unit"** when the column it used was not
  a unit price — something the document does not state either way.
- **The zero-band note missed exactly the case that needed it.** It tested the
  rate plus its adjuster, so a band printed at `0` with an adjuster of `-1.4`
  summed to `-1.4` and carried no note. It now tests the printed rate.
- **Reading a whole table into memory costs about 3× the file size.** A
  1,083 MB published file needed 3.6 GB and 62 seconds. `Cell` now uses
  `__slots__`, which was worth gigabytes; the underlying limit remains and is
  published rather than warned about.

## What an adversarial review found that neither the tests nor the corpus did

The suite was green and both corpora had been measured when a review was
commissioned specifically to break the tool's stated promises. It broke two.

- **Exit 0 was reachable with no arithmetic done at all.** Described above. It
  is the most important promise in the tool and it had a hole in it.
- **The offline guard could be walked past using only allowlisted modules.**
  The allowlist held the top-level package `xml`, and `xml.sax.parse(url,
  handler)` resolves a system id through `urllib.request.urlopen` — a working
  exfiltration path with no socket, no subprocess and no dynamic import
  anywhere in the source. Separately, `zipfile` does `import os`, so
  `zipfile.os` is the real `os` module, and
  `getattr(getattr(zipfile, "o"+"s"), "sys"+"tem")(command)` spawned a shell
  with the whole suite green. The allowlist is now dotted — `xml.etree` and
  nothing else under `xml` — every module name an allowed module re-exports is
  refused as an attribute, and `getattr` is refused outright. Both proofs of
  concept are regression tests.

Four more, none of which the tests would have caught:

- **A corrupt `.xlsx` exited `1`, not `2`.** A zip verifies a part's CRC when
  it is unpacked, not when the archive is opened, and the failure arrives as
  `zlib.error`, which is neither an `OSError` nor a `zipfile.BadZipFile`.
- **`stated-discount` reported a contradiction in a consistent file.** With
  two columns both naming a list price, it bound to the nearer name and
  flagged a row that reconciled perfectly against the other one — and
  reordering the two columns made the finding vanish. Every candidate pairing
  is now tried, and a finding needs all of them to fail.
- **`two-prices` asserted "no other column in this table tells the two rows
  apart"** about a `Promo` column sitting right there. It now says no column
  *this tool recognises* does, and that one it does not recognise may.
- **A sub-header stole the header row.** Taking the last header-shaped row
  handles a title block above the header, which is what published files
  usually have; it fails on a units row or category banner below it. The
  candidate that names the most recognised columns now wins, which handles
  both.

The review also confirmed what it could not break: no output path passes
judgement, no check touches a cost, a blank is never read as a zero, and no
role anywhere is inferred from a column's contents.

## What it misses

Stated plainly, because a checking tool that hides its blind spots is worse
than none. The long version is
[`docs/limitations.md`](docs/limitations.md).

- **Nothing about margin, ever.** A price list does not state a cost.
- **Two of the seven checks are unmeasured.** `bundle-above-parts` and
  `discount-tier` have unit tests and no corpus: nothing found in this work
  publishes a bundle composition or a volume discount ladder in a
  machine-readable price list. They may be wrong in ways nobody has seen.
- **A column name it does not know stops a check.** *Trade*, *Band C*,
  *Kundenpreis* get no role. The report says which word it wanted; `--map`
  settles it. The vocabulary is a record of headers that exist, and it is
  biased towards the corpora this tool has met.
- **A qualifier it does not know produces wrong findings, and not a few of
  them.** If a column that legitimately separates two rows has an unrecognised
  name, `two-prices` and `unit-mismatch` treat those rows as the same thing.
  A published Czech transit fare list shows **2,396** apparent "price falls as
  distance rises" violations when its rows are grouped by tariff and distance
  alone, and **zero** once `validity_days` is part of the group. This is the
  most likely source of a wrong finding on your file, and the failure mode is
  thousands of findings rather than one.
- **It cannot tell a unit price from a line total.** Where no column names a
  unit price it uses the net price and says so in the finding.
- **It holds the whole table in memory.** The largest published file measured
  — 1,083 MB of CSV, 93,954 rows across several hundred payer columns — needed
  **3.6 GB and 62 seconds**. There is no streaming mode, and no cap: a file
  bigger than your memory will not be read, it will swap.
- **One file at a time.** It cannot compare this quarter's price list with
  last quarter's, or with the contract, or with the invoice.
- **It reads values, not formulas.** A number produced by a broken formula is
  checked as the number it now shows.
- **No PDF.**

## Reproducibility

Every number above comes out of a script in `tools/`, against a corpus whose
hash is published. Re-run them:

```bash
curl -sO https://apps.openei.org/USURDB/download/usurdb.csv.gz
shasum -a 256 usurdb.csv.gz     # 9005c5358de7e2471cef...d28d5
python3 tools/measure_corpus.py usurdb.csv.gz
python3 tools/measure_corpus.py usurdb.csv.gz --samples audit.json

python3 tools/fetch_hospital.py corpus/ --count 200 --cap-mb 40
python3 tools/measure_hospital.py corpus/ --samples hospital-audit.json
```

Neither corpus is redistributed here. The tariff export is 195 MB and public
domain; the hospital files are republished constantly and belong to the
hospitals that publish them. What is published is the measurements, the
selection rules, and the hashes that tell you whether you have the same
documents.

A corpus that was collected and then **rejected** is in the manifest too:
1,174,346 published transit fares, across 139 GTFS feeds, in which `fare_id`
is a primary key and every feed uses one currency — so the two checks it was
collected for cannot fire on it even in principle.

## Licence

MIT. See `LICENSE`.

Nothing in this repository is pricing, commercial, legal or financial advice.
