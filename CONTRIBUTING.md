# Contributing

Contributions should improve evidence quality, reproducibility, failure safety,
or clarity. More checks and more output are not automatically improvements.

## Setup

```bash
python3 -m pip install --no-deps .
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

No dependencies, and `pyproject.toml` says `dependencies = []`. A test asserts
that, because the offline guard only reads this package's source and that is
only good enough while there is nothing else in the install to read. If you
need a library, expect to be asked whether the stdlib can do it — the `.xlsx`
reader is `zipfile` and `xml.etree` for exactly this reason.

## Change standard

1. Start from a scoped issue, or explain the observed problem in the pull
   request.
2. Add a failing test for a behaviour change.
3. Make the smallest implementation that passes it.
4. Run the full suite.
5. Update the README, `docs/limitations.md` and `docs/corpus-manifest.md` when
   commands, evidence, limitations or output change.
6. Disclose material AI assistance and confirm that you reviewed the result.

## The rules this repository will not bend on

**No verdicts, ever.** Nothing in the output may say that a price is right,
wrong, high, low, fair, competitive or profitable. Every finding is a statement
about two numbers printed in the same document. `tests/test_checks.py` runs a
file that produces findings from four checks at once and fails if any of
seventeen forbidden words appears in one — *should*, *wrong*, *error*,
*margin*, *profit*, *overpriced*, *recommend* among them. A change that needs one of those words is a
change to the tool's purpose, and belongs in an issue first.

**Nothing that needs a cost.** A price list does not state one. Any check that
would need a cost, a margin, a competitor's price, a market rate or a currency
conversion is out of scope by construction, not by omission.

**A check that did not run is not a check that passed.** `ran` and `findings`
are separate fields and the reason is mandatory when a check does not run.
Switching every check off exits `2`, and so does a file in which no check could
run. A change that lets either reach exit `0` will be closed.

**Roles come from column names, not from column contents.** Inferring that a
column of numbers between 0 and 100 must be a discount is how a tool invents a
contradiction that is not in the document. Contents may be used to *refuse* a
column, never to claim one. The reasoning is in
`docs/superpowers/specs/2026-09-09-adds-up-design.md`.

**An undecidable number is refused, not guessed.** `1,234` is two different
numbers in two conventions. The decision is made once per column from the
cells that are unambiguous, and a column with none is refused.

**Every published number is produced by a script in `tools/`.** If you change
a figure in the README, change the script that prints it and say which corpus
and which hash it came from. A number in the README that nothing re-runs is
the specific failure this rule exists to prevent.

## Adding a column name to the vocabulary

This is the most common useful contribution, and it is welcome. Two conditions:

1. **The name is one a real published price list uses.** Say where you saw it.
   The vocabulary is a record of headers that exist, not of headers that might.
2. **It does not collide with an existing role.** A name that matches two roles
   makes the column ambiguous and unusable, which is worse than not adding it.
   `tests/test_columns.py` is where to prove it does not.

## Adding a check

Harder, and the bar is the same as the existing seven:

- Both halves of the comparison are printed in the input.
- It states what two rows say, and passes no judgement on either.
- It declares the roles it needs and does not run without them.
- It can be measured against a real corpus, or the README says plainly that it
  cannot — as it currently does for two of the seven checks and for half of a
  third.

## Reporting a wrong finding

The most valuable issue you can open. Include the two rows, the column headers
above them, and what the document actually means. A wrong finding is usually a
qualifier column the vocabulary does not know, and that is a one-line fix with
a test.
