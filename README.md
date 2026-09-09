# adds-up

Reads a price list and reports the arithmetic in it that contradicts itself.

Runs entirely on your machine. No account, no API key, no upload, no network
call, no dependencies beyond Python itself.

```
$ adds-up examples/volume-tiers.csv
adds-up 0.1.0 — examples/volume-tiers.csv

6 row(s) under a header read from row 4, the only header-shaped row above the data with data under it; 3 row(s) above it were read as a title block.
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

The reasoning, and every check that was considered and rejected, is in
[`docs/superpowers/specs/2026-09-09-adds-up-design.md`](docs/superpowers/specs/2026-09-09-adds-up-design.md).

## The second thing: a finding is not a defect

The tool reports that two numbers in a document cannot both describe one
consistent price. It does not know which is wrong, or whether either is.

The corpus proved this the hard way. **Inclining block pricing — charging more
per unit as you use more — is deliberate and everywhere in utility tariffs.**
Of thirty volume-tier findings read by hand against 29,521 published tariffs,
all thirty were arithmetically correct and **twenty-nine were not mistakes**:
they were pricing somebody meant to set. The check says a larger band is
priced higher, in those words, and stops.

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
| **two-prices** | The same item is priced twice, differently, and no column this tool recognises tells the rows apart. A free-text note counts as one: two rows carrying different notes are two rows the document is separating. |
| **inverted-range** | A row states a minimum above its own maximum. |
| **unit-mismatch** | One item is priced in two different units, or two different currencies. A document that spans several currencies is normal and is not reported. |

**Every one of these compares two things printed in the input**, and six of
the seven compare numbers. `unit-mismatch` compares text — a unit code against
a unit code — and the report says so beside it, because exit 0 is earned by
arithmetic and that check does none.

None of them uses a cost, a margin, a benchmark, a market rate or a currency
conversion, because a price list states none of those.

### Three narrowings that cost coverage on purpose

**A percentage has two opposite meanings, and only its name decides which.**
*20% off* and *pays 20% of* are contradictory instructions and both appear in
real price lists — the second is how the US hospital price-transparency schema
states a negotiated rate. So there are two roles, and the column's name picks
one. Trying both readings and reporting only when neither fits was rejected:
a check that accepts whichever reading happens to fit can never fail.

**A percentage is only compared with the price it is a percentage of.** Where
a document holds several net-price columns, the percentage pairs only with the
one that is its own name with the last word changed — `…|negotiated_percentage`
with `…|negotiated_dollar` — unless there is exactly one candidate. A published
file puts a discounted cash price beside that pair, and a gross charge times a
negotiated percentage has no reason to equal a cash price; on files that leave
the negotiated dollar column empty throughout, falling back to the nearest
other price produced a finding on every row. If nothing qualifies, the check
declines to run and says so.

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

**Where several columns claim one role, the leftmost whose numbers can be read
wins.** A published standard-charges file carries a cash price and a negotiated
price side by side, and a hospital that publishes only the second leaves the
first empty on every row; taking the leftmost regardless had the check
reporting that it could not run with a usable column beside the one it had
chosen.

**The header row is chosen the same way — by names.** Among the header-shaped
rows in the first 25 that have data under them, the one naming the most
columns this tool recognises wins, and the last one only breaks a tie. That
handles a title block above the header, which is what published files usually
have, and a units row or category banner below it, which is what defeats
taking the last one. The report prints which row it used and why, and
`--header-row` overrides it.

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

`tools/measure_corpus.py`, `tools/measure_hospital.py`, `tools/probe_gtfs.py`
and `tools/audit_hospital.py` are the scripts that produced every number
below.

### Corpus 1 — 29,521 published utility tariffs

The OpenEI U.S. Utility Rate Database, retrieved 9 September 2026, SHA-256
`9005c535…d28d5`. Every rate structure with two or more tiers, from 18,049
distinct tariffs published by 2,062 utilities.

| | |
|---|---|
| Price lists | 29,521 |
| Tier rows in them | 75,969 |
| — carrying a per-unit adjuster, added to the rate before comparing | 32,996 |
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
the only source found where **thousands of column headers were written by
people who have never heard of this tool**.

**It has now been run twice.** The first run's findings were hand-read back
against their files, that audit found three defects in the tool, and the
numbers below are the second run with those fixed. Both runs are reported,
because the difference between them is the most useful thing this corpus has
produced.

| | |
|---|---|
| Files | 200 |
| — CSV | 173 |
| — JSON served from a `.csv` URL, refused by name | 27 |
| Bytes read | 9.28 GB |
| Rows read | 20,513,338 |
| Rows **not** read, cell count not the header line's | **190,549**, in 19 files |
| Unreadable | **0** |
| Crashes | **0** |
| Distinct column names, across the 173 CSVs | **8,519** |
| Columns in them, of which 9,440 were given a role | 13,979 |
| CMS template versions, all in circulation at once | 3.0.0 ×71, 2.0.0 ×66, 2.2.0 ×23, 2.0.2 ×1 |
| Header row chosen | row 3 in 169 files, row 1 in 3, row 4 in 1 |
| Slowest file | 685 MB in 140 s. The largest, 1,083 MB, took 44 s |
| Whole run | 21.4 minutes of analysis, peak RSS 8.93 GB |

**27 of the 200 files are not CSV**, and the tool now says so. They are the
CMS schema's JSON form, served from a URL ending `.csv`. Read as delimited
text, one of them is a single row of up to 1.16 million comma-separated
fields; every check then fails to find a column it can use and the run exits
`2`. That was already the right outcome and nothing was ever invented out of
one — but the reader had to infer *this is not a table* from a header a
million columns wide. A file whose first non-blank character is `{` or `[`
with a JSON key after it is now refused by name, with a message saying so.
It is a shape test and not a parse, so a price list that opened that way and
had a quoted colon early in it would be refused wrongly.

That also settles which column figures are worth quoting. The 173 real CSVs
hold **13,979 columns and 8,519 distinct column names**; 8,519 is the number
this corpus was collected for. The first run, which read the 27 JSON files as
tables, reported 6,852,483 columns and 661,590 distinct names, **99.8% and
98.7% of them JSON punctuation**. Refusing those files removes the figure that
could be quoted for the other.

**190,549 rows were set aside for being the wrong width**, and that line in
the report is new. 190,547 of them carry more cells than the header line;
**2 in the whole corpus** fail the opposite way, not reaching every named
column. 19 files hold at least one.

180,085 are a single file. Sky Lakes Medical Center leaves commas unquoted
inside free text, so 180,084 of its 1,342,453 rows parse to more cells than
its 29-column header and every value after the break sits under a heading
that is not its own. The first run read all of them and said nothing; this
one reads none of them and says how many. After Sky Lakes the largest are St
Joseph of Nashua (7,043 of 45,242) and Mercy Waldron (2,352 of 478,748).

The rule is judged against the header **line**, not against the headings that
have names, and both halves of that were paid for. One file ends its header
line in a comma — 25 headings of which the last is empty, above 1,444,617
rows of 24 cells — so a row that stops short of an unnamed column is fine.
Another ends its header line in three commas and puts a value in the last of
the columns those commas open, so those unnamed columns cannot simply be
dropped. A first version of this rule did drop them and emptied that file of
all 27,356 rows.

### Which checks ran

| check | ran on | why not, where it did not |
|---|---|---|
| **volume-tier** | **0 files** | no column names a quantity or a volume band — in all 173 |
| **discount-tier** | **0 files** | the same column is missing |
| **bundle-above-parts** | **0 files** | no column names the items a bundle is made of — in all 173 |
| stated-discount | 70 | in the 103 it did not: 77 hold a percentage column with no number in it, 21 hold a percentage that pairs with none of their net-price columns, 3 hold one whose writing the document does not settle, 2 name no list price |
| two-prices | 171 | 2 name no item |
| inverted-range | 160 | 11 refuse the number convention in the column, 2 name no bottom of a range |
| unit-mismatch | 170 | 2 name no item, 1 no unit or currency |

**The same three columns are missing from all 173 CSVs: a quantity, a volume
band, and a bundle's composition.** `volume-tier`, which the tariff corpus
exercised 29,205 times, has nothing to work with in a hospital file at all;
`discount-tier` and `bundle-above-parts` have now failed to run on either
corpus and remain untested against any real document. It is not that hospitals
price those things consistently. It is that the document does not state them,
so there is nothing to contradict.

`stated-discount` ran on 70 files rather than the first run's 75. Three of
the five it lost hold nothing but percentage columns every value of which
lies between 0 and 1 — which is 85% in one writing and 0.85% in the other,
with nothing in the document to settle it — so every one of them is refused
and the check declines to run. **22 percentage columns in 4 files** are
refused for that reason, out of the **1,623 columns the run gave a percentage
role**; the fourth file has other percentage columns that are readable, and
the check still runs on it.

### Findings, and how few documents produce them

| check | findings | documents | worst document | its share | top three | median document |
|---|---|---|---|---|---|---|
| stated-discount | 470,549 | 16 | 342,918 | **72.9%** | **97.4%** | 240 |
| two-prices | 189,501 | 52 | 50,616 | 26.7% | 58.1% | 43 |
| inverted-range | 2,614 | 4 | 1,410 | 53.9% | **100%** | 669 |
| unit-mismatch | 1,719 | 12 | 600 | 34.9% | 76.6% | 21 |

**Every one of those totals is more concentrated than it was**, because what
the fixes removed was concentrated: one file's ragged rows, one file's
fractions. `inverted-range` is now four documents and its top three are all of
it. 470,549 is still three hospitals — Nazareth 342,918, Hancock County
85,797, Vibra Central Dakota 29,485, **97.4%** between them, against a median
document of 240. The number is real and it is not a rate: it says three files
are enormous and repetitive. Every count above is published beside its worst
document for that reason, and `--per-document` writes the full list.

`two-prices` is unchanged at 189,501 and is the least concentrated of the
four, and there the concentration is not really about documents. Four of its
five largest — Sycamore Shoals, Hancock County, Russell County and Lonesome
Pine, 117,960 findings between them — share a column layout, a notes wording
and the *same duplicated rows*: `BLADE RESECTOR 3.5`, CDM code 27200002,
appears in all four. That is one vendor's export published by four hospitals,
not four independent measurements of anything.

### The hand audit, and what it says now

Every drawn finding was read back against the file it came from, at the row
and column it names, in both runs. `tools/audit_hospital.py` does the
mechanical half: it re-reads the CSV independently, and — added because of
what the first audit found — it now also confirms the cited row is the header
line's width and re-derives the arithmetic the finding printed, saying which
reading of a percentage column reconciles.

The draw is one finding per document at seed 11, capped at 30, so for three of
the four checks the sample *is* every document that produced the finding at
all. That sounds comprehensive and is not: those are 4, 12 and 16 documents.

| check | read by hand | drawn from | wrong, this run | wrong, first run |
|---|---|---|---|---|
| stated-discount | 16 | **all 16** documents with a finding | **0** | 2 of 17 — **12%** |
| two-prices | 30 + 4 | 30 of 52 documents, plus 2 findings from each of the 2 largest the draw missed — **95.8%** of the check's findings | **0** | 0 of 40 |
| inverted-range | 4 | **all 4** documents with a finding | **0** | 1 of 5 |
| unit-mismatch | 12 | **all 12** documents with a finding | **0** | 2 of 14 — **14%** |

Weighted by findings rather than by documents, counting only causes that were
established across a whole file rather than sampled:

| check | first run | this run | what changed |
|---|---|---|---|
| inverted-range | 1,517 of 4,131 — **36.7%** | **0 of 2,614** | Sky Lakes' 1,517 were all shifted rows; the count fell by exactly 1,517 |
| unit-mismatch | 369 of 2,088 — **17.7%** | **0 of 1,719** | 352 shifted rows and 17 case-only; the count fell by exactly 369 |
| stated-discount | 11,230 of 572,977 — **2.0%** | **0 of 470,549** | Collingsworth's 11,240 fractions are gone entirely |
| two-prices | 0 of 189,501 | **0 of 189,501** | untouched by all three fixes |

The two arithmetic identities are the strongest evidence here: the corpus-wide
finding counts fell by **exactly** the numbers the first audit had proved
false, and by nothing else.

**Read the zeroes as what they are.** They mean no finding in the samples
above was wrong, and that the three causes measured file-wide are gone by
construction. They are not a claim that the rate is zero. `inverted-range`
now rests on **four documents**; `unit-mismatch` on twelve. A fourth cause —
a qualifier column the vocabulary does not know — remains unfixed, and has
not been seen in either audit of this corpus.

What the drawn findings did contain, six times, was a pair of rows differing
only in a column computed *from* the price they disagree about: an
`estimated_amount`, or a `standard_charge|negotiated_algorithm` whose text
quotes the gross charge back ("78% of $604.49 in Billed Charges"). A
difference there is the same fact as the finding, not an explanation of it,
and every one of the six was read by hand to confirm that before it was
allowed to stand.

**One fix removed findings the audit had judged correct.** Vibra Central
Dakota fell from 120,673 `stated-discount` findings to 29,485. The 91,188 it
lost came from percentage columns holding `0.8` throughout, which are now
refused — and the first audit had judged Vibra's sampled finding *correct*,
because that file's `negotiated_dollar` column holds the gross charge on
120,698 of its 120,728 rows, so the rows do contradict themselves whichever
way the percentage is read. Refusing the column stops the tool saying so. That
is the price of not guessing a convention the document does not state, and it
is a real price, not a rounding.

### Right, and not a defect

The other half of the tariff corpus's lesson repeats here. All 16
`stated-discount` findings read this round are true statements about the cells
they quote, and most of them are still not mistakes:

- Four are rounding or an uplift. `31.00% of 4.0000 = 1.24` printed beside a
  negotiated dollar of `1.25`; `100.00% of 1.0000` beside `1.01`;
  `64% of 0.765 = 0.4896` beside `0.48`. Three files state in their own
  `standard_charge|negotiated_algorithm` column, in words, that the negotiated
  dollar is a percentage of the gross charge *and then uplifted* — Hancock
  County's cluster on 1.05, 1.06 and 1.02, which is what that column says. The
  tool does not read it, and would be guessing if it tried.
- That pattern is most of the corpus total. Read back with a flat 0.5%
  tolerance, 229,392 of Nazareth's 879,195 percentage/dollar/gross triples
  fail, and **99.99% of those have a dollar between 0.97 and 1.02 times the
  percentage of the gross charge** — not a contradiction anybody would act on.
- The rest are gaps nothing in the document explains, and some are plainly
  defects: a percentage column filled with `100` beside a dollar that is not
  the gross charge, a negotiated dollar of `52.9` printed identically into the
  percentage column beside it, and — at Nazareth — 64% of $91.00 stated as
  $58.42 where it is $58.24, which is two digits transposed.

### What this corpus cannot establish

**It says nothing about how often a hospital is wrong.** It says what the
document states, and how often the tool reads that correctly. A
`stated-discount` finding is a percentage that does not produce the price
printed beside it; on this corpus that is usually a rounding step or an uplift
the file describes in prose, and only sometimes an error.

**It cannot measure three of the seven checks, and it has now established
why.** `volume-tier`, `discount-tier` and `bundle-above-parts` need a
quantity, a volume band or a composition, and no file in this corpus publishes
any of them — so `volume-tier` rests entirely on the tariff corpus and the
other two rest on nothing but their unit tests. The currency half of
`unit-mismatch` is in the same position: no currency column appears in either
corpus.

**A zero false-positive rate is a statement about a sample.** Where a rate
here comes from a draw it says how many were read, and three of the four
draws are every document that produced the finding at all — which sounds
comprehensive and is not, because those are 4, 12 and 16 documents. The
per-file arithmetic — Sky Lakes' 180,084 ragged rows, Collingsworth's 11,240
fractions, Vibra's 91,188 suppressed findings, Kula's 17 case-only units —
are counts over named files, not estimates over the corpus.

**It is biased towards small hospitals**, by the 40 MB download cap described
in the manifest, and towards whichever vendors those hospitals use: four of
the six documents that produce most of the `two-prices` findings publish one
vendor's export, down to the same duplicated row.

**200 files is not the 5,023 in the index they were drawn from**, let alone
every US hospital. Nothing here establishes what fraction of published
standard-charges files contain any of this.

## What the measurement found that the tests did not

Every one of these was a real defect, found only by meeting real published
files. The suite was green throughout.

**The counts in this section are not reproducible.** They were taken against
the corpora named above with *earlier* versions of this tool, and the current
`tools/` scripts cannot produce them, because the defects they measure are
fixed. They are a changelog with evidence attached, not a measurement — which
is exactly the distinction this repository otherwise insists on, so it is
stated rather than left for a reader to discover that the numbers do not
re-run.

**Three of them were found by hand-reading the first hospital run's findings
back against their files** — 66 findings, one per document for each check.
The suite was green, both corpora had been measured, and an adversarial review
had already been through the tool. They are listed first because they are the
largest of everything on this page, and because the same thing has now
happened on five consecutive tools in this portfolio: meeting real files finds
what tests do not.

- **A row with more cells than the header was read anyway, and silently.**
  This was the largest single source of wrong findings ever measured here. An
  unquoted comma inside a free-text field shifts every value after it into the
  next column, and the tool went on reading whatever now sat under each
  heading. One published file, Sky Lakes Medical Center, carries **180,084
  such rows out of 1,342,453**; every one of the 1,517 rows in it where the
  minimum exceeded the maximum was one of them, and not one well-formed row in
  the file had that defect — **36.7% of the whole corpus's `inverted-range`
  findings**. The same shift supplied all 352 of that file's `unit-mismatch`
  findings, reporting drugs "priced in 2 different units: inpatient,
  outpatient". A row of the wrong width is now not read, and the report says
  how many were set aside and in which file. The corpus-wide counts fell by
  exactly 1,517 and 352.
- **A unit was compared case-sensitively, and the item beside it was not.**
  `ML` on one row and `mL` on another were reported as one drug priced in two
  units — after the two rows had been matched as one item across a description
  differing in case in exactly the same way. All 17 findings in one published
  file, Kula Hospital, were that and nothing else. The unit is now folded like
  the item, and the corpus-wide count fell by exactly 17.
- **A percentage column holding a fraction was read as a percentage.** The CMS
  schema means 85% by `85`; some hospitals write `0.85`. One file,
  Collingsworth General, writes fractions throughout, and **11,230 of its
  11,240 `stated-discount` findings reconciled exactly under the other
  reading**. The fix is not to detect which writing a file uses — that would
  be inferring from contents, which this tool does not do. It is to ask the
  question the number reader already asks of a thousands separator: *does
  anything in the column settle it?* A cell printing `%` does, and so does a
  cell above 1, which a fraction of a price is not. A column in which every
  value lies between 0 and 1 is settled by neither and is refused. Of the
  1,623 columns given a percentage role across the corpus, that is 22 columns
  in 4 files.
- **A JSON document named `.csv` was read as a very wide table.** 27 of the
  200 hospital files are the CMS schema's JSON form served from a URL ending
  `.csv`. No check could find a column it could use and the run exited `2`,
  which was right — but nothing said the file was not a table, and the column
  totals for the whole corpus were 99.8% JSON punctuation. It is refused by
  name now.

Everything below was found by the earlier runs, in the same way.

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
- **A free-text note was not treated as telling two rows apart.** Hand-reading
  thirty `two-prices` findings found **ten** that were two rows identical but
  for a note reading `Gross Charge Type: Sta` against `Gross Charge Type:
  Fee` — a 33% false-positive rate, from one unrecognised column. Recognising
  notes as qualifiers took the count on the same files from **91,760 to
  5,221**, and a re-audit of the survivors found 22 of 22 correct.
- **`drug_unit_of_measurement` holds an amount and `drug_type_of_measurement`
  holds the unit.** The names read the other way round, and reading them that
  way had the tool reporting that a drug was "priced in 2 different units:
  1357.2 and 8".
- **A percentage was compared against a cash price.** Where a file leaves its
  negotiated dollar column empty throughout, the nearest remaining price was
  the discounted cash price — and a gross charge times a negotiated percentage
  has no reason to equal one. A percentage now pairs only with a column that
  is its own name with the last word changed, or declines to run.
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
- **Reading a whole table into memory costs about four times the file size.**
  The largest published file in the corpus, 1,083 MB, needs about 3.9 GB.
  `Cell` now uses `__slots__`, which was worth gigabytes on it; the underlying
  limit remains and is published rather than warned about.

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
- **Two of the seven checks, and half of a third, are unmeasured.**
  `bundle-above-parts` and `discount-tier` have unit tests and no corpus:
  across the 173 hospital CSVs a column naming a bundle's contents appears
  **zero times**, and so does a quantity column, and nothing else found in this work
  publishes either in a machine-readable price list. The **currency** half of
  `unit-mismatch` is in the same position — no currency column appears in
  either corpus, and the transit fares collected specifically to supply one
  turned out never to carry two currencies in a feed. All three may be wrong
  in ways nobody has seen.
- **A column name it does not know stops a check.** *Trade*, *Band C*,
  *Kundenpreis* get no role. The report says which word it wanted; `--map`
  settles it. The vocabulary is a record of headers that exist, and it is
  biased towards the corpora this tool has met.
- **A row of the wrong width is not read, and that has a cost of its own.** A
  row with more cells than the header line is set aside, because an unquoted
  comma in a free-text field puts every value after it under the wrong
  heading; so is a row that does not reach every named column. The report says
  how many and in which file, and 190,549 rows across 19 of the 173 hospital
  CSVs were set aside on the last run. **The cost falls on a file whose
  writer puts a trailing comma on its data rows but not its header**: every
  row in it is one cell too wide, none is read, and the run exits `2` saying
  so. Loudly wrong is the intended failure here, but it is still a file this
  tool will not read.
- **A percentage column that could be either writing is refused, and a real
  finding can go with it.** One published file lost 91,188 `stated-discount`
  findings that the hand audit had judged correct, because the percentage
  column they came from holds `0.8` throughout and nothing in the document
  says whether that is 80% or 0.8%.
- **A qualifier it does not know produces wrong findings, and not a few of
  them.** This one is still open. If a column that legitimately separates two
  rows has an unrecognised name, `two-prices` and `unit-mismatch` treat those
  rows as the same thing. A published Czech transit fare list shows **2,396**
  apparent violations when its rows are grouped by tariff and distance alone,
  and **zero** once `validity_days` is part of the group. The failure mode is
  thousands of findings rather than one. It was expected to be the commonest
  cause of a wrong finding; on the hospital corpus it has now caused none in
  two hand audits of 66 findings each.
- **It cannot tell a unit price from a line total.** Where no column names a
  unit price it uses the net price and says so in the finding.
- **It holds the whole table in memory.** The largest published file in the
  corpus — 1,083 MB of CSV, 93,954 rows of 285 columns — needs about **3.9 GB
  and 44 seconds** on its own, on the machine these numbers were taken on
  (macOS, CPython 3.14). That is roughly four times the file size. Across the
  whole 200-file run, peak resident memory reached **8.97 GB**, and **6.9 to
  8.5 GB** on the three earlier runs. There is no streaming mode and no cap: a
  file bigger than your memory will not be read, it will swap.
- **One file at a time.** It cannot compare this quarter's price list with
  last quarter's, or with the contract, or with the invoice.
- **It reads values, not formulas.** A number produced by a broken formula is
  checked as the number it now shows.
- **No PDF.**

## Reproducibility

Every corpus-wide number above comes out of a script in `tools/`, against a
corpus whose hashes are published, and the two exceptions are named below.
Re-run them:

```bash
curl -sO https://apps.openei.org/USURDB/download/usurdb.csv.gz
shasum -a 256 usurdb.csv.gz     # 9005c5358de7e2471cef...d28d5
python3 tools/measure_corpus.py usurdb.csv.gz --samples tariff-audit.json

python3 tools/fetch_hospital.py corpus/ --count 200 --cap-mb 40
python3 tools/measure_hospital.py corpus/ --samples hospital-audit.json \
    --per-document concentration.json
python3 tools/audit_hospital.py corpus/ hospital-audit.json

python3 tools/probe_gtfs.py --feeds 140
```

**Two exceptions, both flagged rather than glossed.** The survey of open data
portals — 3,802 URLs, 43 price-list titles, a 1.7% true-positive rate — was a
one-off reconnaissance across six portals whose APIs differ and whose result
sets are capped by relevance. No script reproduces it; the API forms are
published so it can be repeated by hand.

The second is the per-file arithmetic in the hospital audit — Collingsworth's
11,230, Sky Lakes' 1,517 inversions and 352 unit findings, Kula's 17,
Nazareth's ratio spread, Vibra's 120,698 — which was done by hand while
reading each finding back against its file, not by a script in `tools/`. Each
is one pass over one named file and each is stated as the operation that
produced it: for Sky Lakes, count the rows whose cell count differs from the
header line's and check which of them carry a minimum above their maximum; for
Collingsworth, divide the negotiated dollar by the gross charge and compare it
with the percentage cell as written and as divided by a hundred. They are
counts over a single document rather than measurements of a corpus, which is
why they are named here instead of being given a flag.

**Sky Lakes' 180,084 ragged rows are no longer in that category.** The tool
counts them itself now, prints the count, and `measure_hospital.py` totals it
across the corpus, so that figure comes out of the run like every other. The
same is true of the 22 refused percentage columns.

Neither corpus is redistributed here. The tariff export is 195 MB and public
domain; the hospital files are republished constantly and belong to the
hospitals that publish them. What is published is the measurements, the
selection rules, and — in
[`docs/hospital-corpus.csv`](docs/hospital-corpus.csv) — the SHA-256 of every
one of the 200 hospital files, beside its certification number, facility name
and URL. That file is a bibliography: no price, no charge, no row of anyone's
chargemaster, no personal data.

A corpus that was collected and then **rejected** is in the manifest too:
1,174,347 published transit fares across 140 GTFS feeds, in which `fare_id` is
a primary key and no feed uses more than one currency — so the two checks it
was collected for cannot fire on it even in principle. Twelve currencies
appear across those feeds, and never two in one.

## Licence

MIT. See `LICENSE`.

Nothing in this repository is pricing, commercial, legal or financial advice.
