# Limitations

The short version is in the README. This is the detail, for anyone deciding
how far to trust a result.

## The tool answers one question only

*Do the numbers printed in this price list contradict each other?*

It does not answer, and cannot answer:

- Is this price right?
- Is it profitable?
- Is it competitive?
- Is the discount too generous, or not generous enough?
- Should the tiers be shaped differently?
- Is this what we agreed with the customer?

Every one of those needs at least one number the document does not contain: a
cost, a competitor's price, a volume forecast, a contract, an intention. A
price list states none of them.

**In particular, nothing here is about margin.** A price list does not state a
cost, so the tool has no way to compute a margin and does not try. That is a
boundary, not an omission — a tool that guessed at cost in order to say
something about margin would be worse than one that says nothing.

## A finding is not a defect

This is the most likely way to misread the output.

The tool reports that two statements in a document cannot both describe a
single consistent price. It does not know which of them is wrong, or whether
either is. Both may be exactly as intended.

The clearest case is the volume-tier check. **Inclining block pricing —
charging more per unit as consumption rises — is a deliberate and ubiquitous
design in utility tariffs**, and in the reference corpus of 29,521 published
tariffs it is what almost every volume-tier finding turns out to be. Those
findings are arithmetically correct and are not mistakes. The check reports
that a larger band is priced higher, in those words, and stops there.

The same applies elsewhere. A bundle above the sum of its parts may be a
service package. The same item at two prices may be a legacy row somebody
meant to keep. What the tool does is put the two rows in front of a person who
can tell.

## What a check that did not run means

A check that did not run has found nothing **because it was not made**.

The report lists every check with `ran` or `DID NOT RUN` and a reason, and the
JSON keeps them as separate fields. A run in which no check ran at all exits
`2`, not `0`, and so does a run with every check switched off. A green result
over a price list nothing was compared in is the single outcome this tool
exists not to produce.

Absence of a column is never reported as a defect in the document. "No column
names a discount percentage" is a statement about what this tool could read,
not a criticism of the price list.

## What the column vocabulary can and cannot see

**Roles come from names.** The tool reads the word at the top of each column
and looks it up. It does not infer a role from the shape of the contents,
because a column of numbers between 0 and 100 is equally likely to be a
discount percentage, a case pack, a quantity break or a stock figure, and
choosing one on that evidence is how a tool invents a contradiction.

The cost is silent misses. A column called *Trade*, *Band C*, *Kundenpreis* or
*Tarif spécial* gets no role, and the checks that needed it do not run. The
report says which word it was looking for; `--map` settles it; `--list-columns`
prints everything the tool knows.

**The vocabulary was extended after meeting real files.** Names such as
`standard_charge|gross`, `negotiated_dollar`, `drug_unit_of_measurement`,
`payer_name` and `modifiers` are in it because published files use them, not
because they were imagined. That is honest but it also means the vocabulary
reflects the corpora this tool has met, and a trade in an industry it has not
met will fare worse.

**Two names could not be settled by the name.** A column called `max` is the
top of a volume band in a tier table and the top of a price range in a rate
sheet. The rule is that a bound is a range end only when a column naming the
other end is present, and a quantity otherwise. The report prints which
reading it took. It will be wrong on a table that prints a price ceiling with
no floor, or a band top beside an unrelated `min`.

**Where several columns claim the same role, the leftmost is used**, and the
report names it. On a file with fifty payer columns, the item, quantity and
price used are the first of each. `--map` and `--sheet` are the way to point
at a different one.

## What the number reader can and cannot do

**A separator is decided per column, not per cell.** `1,234` is 1234 in one
convention and 1.234 in the other. A column with no unambiguous cell in it is
**refused**, and the checks that needed it do not run.

Two shapes are decidable and are decided: a leading zero cannot be a thousands
group, so `0.091` is a decimal; and more than three digits in front cannot be
a group either, so `1234.567` is a decimal. What remains genuinely
undecidable is one separator, exactly three digits after it, one to three
digits in front: `1.234`. That is refused.

**A blank is never a zero.** `""`, `-`, `—`, `N/A`, `nil`, `TBD`, `#N/A` and
their friends all mean *nothing was printed*. A row with a blank maximum is
not a row with a maximum of zero.

**Precision comes from the printing.** The tolerance in the discount check is
half of the last printed digit on each input, propagated through the
multiplication. So `33.33%` off `100.00` reconciles with `66.67`. A document
that prints a discount as a whole number gives a wide tolerance — `15` on a
list price of `100.00` allows anything from `84.50` to `85.50` — and the check
is correspondingly less sensitive on such a file. The allowance is printed
with every finding.

**In an `.xlsx` the tool reads the stored value, and the displayed precision
from the cell's number format.** It quotes the stored value in the finding, so
a cell displaying `42.50` and storing `42.50425` appears in the report as
`42.50425`. The tolerance is right; the quotation may surprise a reader
comparing it with what Excel shows them.

## What it does not read

**PDF.** A price list in a PDF is a page of positioned glyphs, and
reconstructing rows and columns from it is a separate problem with its own
error rate. Every finding would then carry two uncertainties — did the
document contradict itself, and did the extractor read it correctly — with no
way to tell which one you were looking at. The tool says it does not read
PDFs rather than reading them badly.

**Formulas.** It reads values only. A workbook whose numbers were produced by
a broken formula, a typed-over cell or a `SUM` that stops a row short will
still be checked against the values it now shows, and those values may be
consistent with each other and wrong. That is a different question, and
`show-your-work` in this same portfolio is the tool that asks it.

**A second document.** Every comparison is inside one file. It cannot tell you
that this quarter's price list disagrees with last quarter's, or with the
contract, or with the invoice.

**Anything about the world.** No currency conversion, no market data, no
benchmark, no index.

## Where a finding can come from bad input rather than a bad price list

- **A header row chosen wrongly.** The tool takes the last header-shaped row
  in the first 25 with data under it. A price list with an unusual title block
  can defeat that; the report always prints which row it used and why, and
  `--header-row` overrides it.
- **A merged or multi-block sheet.** A file holding two price lists stacked in
  one sheet will be read as one, and the second block's header row becomes a
  data row.
- **A column whose name means something else in this trade.** `Rate` is a unit
  price in most price lists and an interest rate in some.
- **A qualifier the tool does not know.** If a column that legitimately
  separates two rows has an unrecognised name, `two-prices` and
  `unit-mismatch` will treat those rows as describing the same thing. This is
  the most likely source of a wrong finding on a real file.

## What the offline promise does and does not cover

Nothing on the analysis path can import a module that opens a connection or
starts a process. `tests/test_offline.py` reads the package's source and
refuses one: imports are an allowlist of eleven modules, the process-launching
parts of `os` are refused by name wherever they appear, the dynamic hatches
are refused, and any file in the package that is not readable Python source
fails the suite.

What it cannot see is **the filesystem**. Reading files is the whole job, so
`pathlib` and `open` are allowed, and no static read can tell a local path
from a network one: an SMB or NFS mount, a UNC path or a FUSE filesystem
reaches the network with no socket call in this package's own source. That is
a real gap, and it is written down here rather than left to be discovered.

It is also a static read, not a sandbox. It does not run the code, and a name
assembled at runtime from pieces never appears in the source for it to find.

## Scope

One file at a time, read as values, compared only with itself. Nothing in this
repository is pricing, commercial, legal or regulatory advice.
