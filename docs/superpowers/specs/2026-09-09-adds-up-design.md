# adds-up — design

9 September 2026.

## What it is

A tool that reads a price list and reports the arithmetic in it that
contradicts itself. Both halves of every comparison come out of the document
it was handed. It never says a price is right, wrong, competitive, fair or
profitable.

## The constraint everything else follows from

**A price list does not state a cost.**

That one sentence decides the whole scope. Every question a person actually
wants to ask about a price list — is this profitable, is it competitive, is
the discount too generous, should tier 3 be cheaper — needs at least one
number the document does not contain. A cost, a competitor's price, a volume
forecast, a strategy.

So the tool cannot answer any of them, and the design refuses to let it look
as though it might. There is no margin, no benchmark, no scoring, no severity,
no "recommended" anything. What is left is the set of statements a document
makes that cannot all be true at once, and those turn out to be worth
reporting on their own: a tier that inverts, a percentage that does not
reconcile with the two numbers printed either side of it, a minimum above its
own maximum.

The test `NothingIsJudged` in `tests/test_checks.py` runs a file that produces
findings from four checks at once and fails if any of seventeen words appears
in one — *should*, *wrong*, *error*, *margin*, *profit*, *overpriced*,
*recommend* among them. It is the only test in the suite that guards a value
rather than a behaviour, and it is there because the temptation is constant.

## The two things that are actually hard

Neither of them is the arithmetic. The arithmetic is a subtraction.

### 1. A price list has no schema

Every one is a different shape. The tool has to decide what each column is
before it can compare anything, and there are exactly two honest ways to do
that: ask the user, or read the name the user already wrote at the top of the
column.

The design does the second and falls back to the first.

**Roles come from names, never from the shape of the contents.** A column of
numbers between 0 and 100 could be a discount percentage, a case pack, a
quantity break or a stock figure. Choosing one because the numbers look right
is how a tool invents a contradiction that is not there. Contents are used
only to *refuse*: a column named like a price whose numbers cannot be read is
reported as recognised-and-unusable, and the checks that wanted it do not run.

**A name that matches two roles matches neither.** The column is reported as
ambiguous with both candidates named, and `--map` settles it.

**One ambiguity could not be settled by the name at all, and is settled by the
rest of the table.** A column called `max` is the top of a volume band in a
tier table and the top of a price range in a rate sheet. Nothing inside the
word decides it. The rule is that a bound is a range end only when a column
naming the other end is present, and a quantity otherwise — and the report
prints which reading it took and why. `from` and `to` are deliberately outside
that rule: in every price list met while building this they name a band of
quantity, and reading them as a price range would be wrong every time.

The whole vocabulary is printed by `adds-up --list-columns`, because a
vocabulary a user cannot read is indistinguishable from a guess.

### 2. A printed number does not always mean one thing

`1,234` is 1234 in a document written for the United States and 1.234 in one
written for Germany. Staring at that cell does not settle it.

So the convention is decided **once per column**, from the cells in that
column that are unambiguous, and a column in which no cell is unambiguous is
**refused** — the checks that needed it do not run, and the report says why.
Guessing here does not produce one wrong number; it produces a confident
finding about a contradiction that does not exist.

Two refinements came out of meeting the corpus rather than out of thinking:

- **A leading zero cannot be a thousands group.** `0.091` is a decimal under
  both conventions, because nobody writes `0,091` to mean ninety-one. Before
  this rule, 1,898 real tariffs whose every rate looks like `0.091` were
  refused as undecidable.
- **More than three digits in front cannot be a group either.** `1234.567`
  is a decimal. A group is exactly three digits.

What is left genuinely undecidable is the narrow case: one separator, exactly
three digits after it, one to three digits in front, no leading zero. `1.234`.
That one is refused, and it should be.

**Precision is carried, not discarded.** `10.00` and `10` are the same number
and not the same printed value. The tolerance in the discount check is derived
from the precision the document itself prints — half of the last printed digit
on each input, propagated through the multiplication — rather than from a
constant somebody picked. A number stored in an `.xlsx` gets its precision
from the cell's number format, which is why the XLSX reader parses
`styles.xml` at all.

## Format scope, and why

**CSV, TSV and XLSX. Not PDF.**

A tabular file gives the tool a grid it did not have to reconstruct. A PDF
price list gives it a page of positioned glyphs, and turning those back into
rows and columns is a whole separate problem with its own error rate. Every
finding would then carry two uncertainties — did the document contradict
itself, and did the extractor read it correctly — with no way for a reader to
tell which one they were looking at. That is a worse tool than one that says
plainly that it does not read PDFs, so it says that, in the error message and
in the README.

XLSX is read with `zipfile` and `xml.etree`. An `.xlsx` is a zip of XML, only
cell values and number formats are needed, and the package's offline guarantee
is a static read of its own source — which is only worth anything because
there is nothing else in the install to read. A dependency would have cost
that.

## It does not collide with `show-your-work`

Both read spreadsheets. They ask opposite questions.

`show-your-work` asks **how the workbook was built**: a formula someone typed
over, a `SUM` that stops a row short, a cell doing something different from
its column, a hidden sheet, a stale link. It needs formulas, so it needs
`.xlsx`, and it says nothing about what the numbers mean.

`adds-up` never looks at a formula. It reads the values as printed and asks
whether the *pricing* they state is self-consistent. It works on a CSV, which
has no formulas at all, because it never wanted them.

A workbook can be perfectly built and price tier 3 above tier 2. A workbook
can have a broken `SUM` and price everything consistently. Neither tool finds
the other's findings, and running both on the same file is reasonable.

## The seven checks

Each is independently switchable, and the report always prints which ran and
which did not, with the reason. A check that did not run must never read as a
check that found nothing — that is why `ran` and `findings` are separate
fields, and why the reason is mandatory.

**And `ran` is not what exit 0 is gated on.** A `CheckRun` also carries the
number of pairs of *numbers* it actually compared, and a run that compared
none exits 2. The two are different, and an adversarial review found the gap
between them: `unit-mismatch` needs no numbers at all, so a price list with a
genuine inverted tier — whose price column had a heading the vocabulary did
not know — exited 0 because the units were consistent. One check had "run".
Nothing had been compared.

| | needs | reports |
|---|---|---|
| **volume-tier** | a quantity and a price | a larger quantity priced higher than a smaller one |
| **discount-tier** | a quantity and a discount percentage | a larger quantity given a smaller discount |
| **bundle-above-parts** | a stated composition, an item and a price | a bundle above the sum of the parts this document prices |
| **stated-discount** | a list price, a net price and a percentage | a percentage that does not produce the second price from the first |
| **two-prices** | an item and a price | the same item priced twice, differently, with nothing telling the rows apart |
| **inverted-range** | a minimum and a maximum | a stated minimum above its own stated maximum |
| **unit-mismatch** | an item and a unit or currency | one item priced in two units, or two currencies |

### Decisions inside them worth writing down

**A percentage may only be compared with the price it is a percentage of.**
Where a document holds several net-price columns, the percentage pairs only
with the one that is its own name with the last word changed —
`…|negotiated_percentage` with `…|negotiated_dollar` — unless there is exactly
one candidate, in which case there is nothing to choose between. A published
file puts a discounted cash price beside that pair, and a gross charge times a
negotiated percentage has no reason whatever to equal a cash price. Where a
file left its negotiated dollar column empty throughout, falling back to the
nearest other price produced a finding on every row of it.

If nothing qualifies, the percentage cannot be placed and the check says so.
That is a check declining to run, which is a different thing from a check
finding nothing, and the report keeps them apart.

**A finding needs every candidate pairing to fail, not the nearest one.**
Where two columns both name a list price, binding the percentage to the nearer
name reported a contradiction in a row that reconciled perfectly against the
other column — and swapping the two columns made the finding disappear. So
every candidate list price is tried against every candidate net price, and a
finding is reported only when none of them reconciles. The finding then names
the pairing it quotes and says how many were tried.

This costs sensitivity: a file with two list prices, one of which happens to
reconcile by coincidence, is now silent. That is the right way round. A tool
whose findings depend on column order is not reporting a property of the
document.

**A percentage has two opposite readings and only its name tells them apart.**
*20% off* and *pays 20% of* are contradictory instructions, and both are
printed in real price lists — the second is how the US hospital
price-transparency schema states a negotiated rate. So there are two roles,
`discount_percent` and `percent_of_list`, decided by the column's name.

The alternative — try both readings and report only if neither reconciles —
was rejected. It cannot fail: a check that accepts whichever interpretation
happens to fit will never find anything, which makes it a check in name only.

**Ordering by quantity has to survive a blank.** A tier table's last band
routinely prints no upper bound because it has none. When exactly one row in a
group leaves the quantity blank and it is the last row as printed, it is read
as that open-ended top band. Any other blank leaves the row's place in the
order unestablished, so it is set aside and *counted*, not guessed at, and the
count appears in the report under *seen and not judged*.

**A blank is never a zero.** `""`, `-`, `—`, `N/A`, `nil`, `TBD` and `#N/A`
all mean nothing was printed. Treating any of them as zero would make every
incomplete row an inverted range.

**A free-text note is a qualifier.** A note attached to a row is by
definition something about that row the other columns do not say, so two rows
carrying different notes are two rows the document itself is separating. This
was not a design decision; it came out of a hand audit in which ten of thirty
`two-prices` findings were pairs of rows identical but for a note reading
`Gross Charge Type: Sta` against `Gross Charge Type: Fee`. Recognising notes
took the count on the same files from 91,760 findings to 5,221, and a re-audit
of the survivors found 22 of 22 correct.

The cost is real and worth naming: a genuine duplicate whose notes happen to
differ trivially is now silent. That is the right direction for a tool whose
findings are accusations.

**Qualifiers are part of an item's identity.** A price list that quotes one
product in GBP for the UK and EUR for the EU is a normal document. So
`two-prices` and `unit-mismatch` both hold every recognised qualifier column
equal — region, customer, plan, date, size, variant — and report only where
the document says two things about the *same* row identity. `unit-mismatch`
did not do this at first and reported every multi-currency price list as
broken.

**The quantity column is part of that identity too.** Without it, every volume
price list is one long `two-prices` finding.

**Where several columns name a quantity, the leftmost is used** and the report
names it. A tier table often prints both an ordinal (`tier`) and a threshold
(`max`); both are quantities and either orders the ladder correctly.

**An adjustment column is added to the rate.** A per-unit adder is part of the
per-unit price, and comparing bare rates while one band carries an adder and
another does not compares two different things. 32,996 of the 75,969 tier rows
in the reference corpus carry one.

## What was considered and rejected

**Anything involving a cost or a margin.** Ruled out by the first section, and
worth stating as a rejection rather than an omission: this is the check a user
will most want and the one the document cannot support. Said in the README as
a boundary, not an apology.

**Comparing prices between two files.** A second price list would answer real
questions — what changed since last quarter, does the quote match the
contract. It is a different tool: it needs a matching key between documents,
and every finding then depends on whether the match was right. Not in 0.1.

**Detecting a column's role from its contents.** Rejected under the same
reasoning as the number-convention rule. A column of values between 0 and 1
looks exactly like a discount fraction and is very often a share, a rate or a
proportion of something else entirely.

**"This tier is only 2% cheaper, which is probably a typo for 20%."** This is
the most tempting rejected check, because it would find real mistakes. It
requires a belief about what the pricing was meant to be, which is the one
thing the document does not state. It would also be right often enough to be
trusted and wrong often enough to be dangerous.

**Flagging a price that is an outlier within its column.** Same objection. A
price list legitimately spans four orders of magnitude.

**Round-number detection** (`£100.00` beside `£97.43` and `£102.18`). An
opinion about pricing psychology, not arithmetic.

**Checking a total against the sum of its lines.** A real and useful check —
and it is `show-your-work`'s, which already does it against the formula that
was supposed to compute it. Duplicating it here on values alone would be a
worse version of an existing tool in the same portfolio.

**Fuzzy matching on column names.** Edit distance would let *Unt Price* and
*Discnt %* through, and it would also let *Net weight* through as a net price
and *List position* through as a list price. A wrong role is worse than no
role, because no role produces a check that did not run and says so, while a
wrong role produces confident findings about the wrong two columns. `--map` is
the answer to a typo.

**An extended-price check** — does `quantity x unit price` equal the line
total, does `area x price per square metre` equal the price. This is the most
serious omission in 0.1 and it is left out for scope, not for principle: it is
pure arithmetic on printed values, exactly like the seven, and the survey of
open data portals found it live in the wild. A Campania public-works price
book holds `base price + overheads + profit = final price` in 12,708 of 12,708
parseable rows; a Polish developer price list, whose form is set by statute,
holds `usable area x price per square metre = price` in 99 of 99 — and fails
against its *other* area column, which is the interesting part. Any
implementation would have to pick the right multiplicand and would need a role
for a line total, distinct from a unit price, that the vocabulary does not yet
have.

**Currency conversion.** Any check that needs a rate needs a number from
outside the document, and a rate has a date.

**A document-wide currency check** — "this file mixes GBP and EUR". Normal,
and not a contradiction. Narrowed to one item priced in two currencies.

**Treating an inclining volume tier as an error.** It is not one. Inclining
block pricing is deliberate and ubiquitous in residential utility tariffs. The
check reports that a larger band is priced higher, in those words, and the
README publishes how often that turns out to be policy rather than a mistake.

## Choosing the header row

Two shapes fight over the slot and no single row can be told from the other.

A published file often has a **title block above** the header. The CMS
standard-charges template puts metadata names on row 1, metadata values on row
2 and the real column names on row 3, and all three are header-shaped. Taking
the *last* candidate handles that, and almost every file in the hospital
corpus needs it — `measure_hospital.py` reports the distribution of the rows
actually chosen under `header_row_chosen`, and the README prints it.

A price list just as often has a **sub-header below** — a units row, a
category banner, a second language. There the last candidate is the wrong one,
and a review demonstrated one stealing the slot from the real header, which
demoted three recognised columns to a title block.

The rule is now: among the header-shaped rows with data under them, the one
that names the most columns this tool recognises wins, and the last one only
breaks a tie. The score is a function of *names* — it is the column vocabulary
applied to a row — so it does not weaken the rule that a role comes from what
a column is called.

## Offline boundary

Nothing on the analysis path can import a module that opens a connection or
starts a process. `tests/test_offline.py` reads the package's own source and
refuses one: imports are an allowlist of eleven modules, the process-launching
parts of `os` are refused by name wherever they appear, the dynamic hatches
are refused, and anything in the package that is not readable Python source
fails the suite — because a compiled extension would be equally importable and
contain nothing to parse.

`os` is not on the allowlist at all. Nothing here writes a file, so the
exception `os` usually needs is not needed either.

**The allowlist is dotted, and that is not fussiness.** An earlier version
allowed the top-level package `xml`. `xml.sax.parse(url, handler)` resolves a
system id through `urllib.request.urlopen`, so allowing `xml` allowed a
working exfiltration path with no socket, no subprocess and no dynamic import
anywhere in the source — and a review wrote it, dropped it into the package,
and watched the whole suite stay green. `xml.etree` is what this package uses
and `xml.etree` is what it may have.

**A module can be reached through another module.** `zipfile` does
`import os`, so `zipfile.os` is the real `os` module and
`getattr(getattr(zipfile, "o"+"s"), "sys"+"tem")(command)` spawns a shell with
no forbidden name anywhere in the source: the attribute names are assembled
from string fragments. Two things close it — every module name an allowed
module re-exports is refused as an attribute, and `getattr` is refused
outright, because this package has no legitimate use for it. Both proofs of
concept are now tests.

What the guard cannot see is **the filesystem**. Reading files is the whole
job, so `pathlib` and `open` are allowed, and no static read can tell a local
path from a network one: an SMB or NFS mount, a UNC path or a FUSE filesystem
reaches the network with no socket call in this package's source. That is a
real gap. It is written in the test's own docstring and in
`docs/limitations.md` rather than left to be discovered.

## What the measurement changed

Written up in full in the README. The short version: the reference corpus
found defects a green test suite did not.

- **`0.091` was called an undecidable separator.** 1,898 real tariffs were
  refused because the rule about ambiguity had never met a price under one
  unit.
- **`unit-mismatch` reported every multi-currency price list.** It ignored the
  qualifier columns that legitimately separate the rows.
- **A malformed `.xlsx` raised a `KeyError` out of `zipfile`** instead of the
  message that says what the tool reads.
- **The `volume-tier` finding said "per unit"** even when the price column it
  had used was not a unit price, which the document does not state either way.
  It now names the column and says so.

## What the review changed

Separately from the corpus, an adversarial review was commissioned to break
the seven promises. It broke two — the exit-0 gate and the offline guard, both
described above — and found four more defects a green suite had not:

- a corrupt `.xlsx` exited 1 rather than 2, because a zip's CRC failure
  arrives as `zlib.error`, which is neither `OSError` nor `zipfile.BadZipFile`;
- `stated-discount` bound to one list-price column by name proximity;
- `two-prices` claimed "no other column in this table tells the two rows
  apart" about a column it simply had no name for;
- a sub-header row could steal the header slot.

It could not break the other five promises: no output path passes judgement,
no check touches a cost, a blank is never read as a zero, no role is inferred
from contents, and it found no realistic price value that reads wrong rather
than being refused.
