# Examples

Four small files. Every one is invented, because no customer, supplier or real
company appears in this repository, and each exists to show one thing.

Rebuild the workbook with `python3 make_examples.py`. It writes the `.xlsx`
with `zipfile` and no dependencies, which is also how the tool reads it.

| file | what it is for | exit |
|---|---|---|
| `volume-tiers.csv` | a title block above the header, and one tier that inverts | 1 |
| `discount-schedule.csv` | a discount that does not reconcile, the same item twice, and one item in two currencies | 1 |
| `rate-card.xlsx` | an `.xlsx` whose stored values are more precise than its display, a shrinking discount, and a minimum above its maximum | 1 |
| `consistent.csv` | everything agrees; five checks run, compare 11 pairs of numbers, and report nothing | 0 |

```bash
adds-up volume-tiers.csv
adds-up discount-schedule.csv --format markdown
adds-up rate-card.xlsx
adds-up consistent.csv      # exit 0
```

## What to look at in the output

**The `CHECKS` block, before the findings.** On `volume-tiers.csv` three
checks run and four do not, each with a reason. That block is the point of the
tool as much as the findings are: a check that did not run has found nothing
because it was not made.

**The `COLUMNS` block.** It says what each column was taken to be and why,
including which reading it took of the numbers in it. If a finding looks
wrong, this is where the cause usually is.

**`consistent.csv` exits 0 and says what that means**, printing "a statement about the
checks that ran, listed above, and about nothing else". It does not say the
price list is fine. Note the comparison count beside it: exit 0 is earned by
arithmetic having happened, not by checks having reported that they ran.

## Two things these files deliberately do not show

**A bundle above the sum of its parts.** The `bundle-above-parts` check needs
a column naming what a bundle contains, and no example carries one, because no
corpus this tool was measured against carries one either. Writing an example
for it would make an unmeasured check look tested. The check has unit tests;
it has no measurement, and the README says so.

**Anything about margin.** None of these files states a cost, because no price
list does.
