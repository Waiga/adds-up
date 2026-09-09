#!/usr/bin/env python3
"""Checks a drawn sample of hospital-corpus findings back against the files.

A hand audit of thirty findings means opening thirty files and reading two
rows in each. This does the mechanical half of that — going back to the row
the finding names and reporting what the two rows actually hold — so the
judgement is made on the evidence rather than on the finding's own summary.

It is not a second opinion from the same code. It re-reads the CSV with
``csv.reader``, locates the rows by the numbers printed in the finding, and
prints every column in which they differ. Whether a difference *matters* is
the part a person still has to decide, and that is the whole point.

    python3 tools/measure_hospital.py corpus/ --samples audit.json
    python3 tools/audit_hospital.py corpus/ audit.json

Verdicts printed per check:

``agree``       the two rows hold the same value in every column this tool
                could read, so the finding stands
``derived``     they differ only in columns computed from the price itself
                (an estimated amount, a median, a percentile), which is a
                consequence of the difference and not an explanation of it
``distinguished`` a column the tool has no name for holds different values,
                so the document may well be separating the two rows and the
                finding is probably wrong
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adds_up.columns import classify  # noqa: E402

csv.field_size_limit(10 ** 9)

#: Columns whose value follows from the price, so a difference in them is the
#: same fact as the finding rather than a reason to doubt it.
DERIVED = ("estimated_amount", "median_amount", "10th", "90th", "count")

TWO_ROWS = re.compile(r"on row (\d+) and at \S+ on row (\d+)")
ONE_ROW = re.compile(r"row (\d+)")
ROW_IN_PLACE = re.compile(r"row (\d+)")


def header_of(rows: list[list[str]]) -> tuple[list[str], int] | tuple[None, None]:
    for index, row in enumerate(rows[:25]):
        if any("standard_charge" in cell for cell in row):
            return row, index
    return None, None


#: The roles whose difference *is* the finding, per check. Reporting them as
#: something that distinguishes the rows would mark every finding wrong.
PRICES = {
    "net_price", "list_price", "unit_price", "minimum", "maximum",
    "discount_percent", "percent_of_list", "adjustment",
}
REPORTED = {
    "two-prices": PRICES,
    # For unit-mismatch the unit is the finding, and a different unit is
    # expected to carry a different price, so neither counts against it.
    "unit-mismatch": PRICES | {"unit", "currency"},
}


def audit_two_rows(rows, header, first, second, check) -> tuple[str, list]:
    left = rows[first - 1]
    right = rows[second - 1]
    roles = {column.index: column.role for column in classify(header)}
    differ = []
    for index, name in enumerate(header):
        a = left[index].strip() if index < len(left) else ""
        b = right[index].strip() if index < len(right) else ""
        if a == b:
            continue
        # The column the finding is about is expected to differ.
        if roles.get(index) in REPORTED.get(check, set()):
            continue
        differ.append((name, a, b))
    if not differ:
        return "agree", []
    if all(name.startswith(DERIVED) for name, _, _ in differ):
        return "derived", differ
    return "distinguished", differ


NUMBER = re.compile(r"-?\d[\d,]*\.?\d*")
PLACE = re.compile(r"row (\d+), (.+)$")


def effective_header(rows: list[list[str]]) -> tuple[list[str], int] | tuple[None, None]:
    """The header, with trailing empty headings dropped.

    A trailing comma on the header line names no column. One file in the
    corpus has 25 headings of which the last is empty above 1,444,617 rows of
    24 cells, and counting the empty one would call every row in it ragged.
    """
    header, index = header_of(rows)
    if header is None:
        return None, None
    trimmed = list(header)
    while trimmed and not trimmed[-1].strip():
        trimmed.pop()
    return trimmed, index


def row_is_well_formed(rows: list[list[str]], header: list[str], number: int) -> bool:
    """Whether the cited row has exactly as many cells as the header names.

    This is the check that was missing when the corpus was first measured. A
    row with more cells than the header has every value after the break under
    a heading that is not its own, and 1,517 inverted ranges — 36.7% of that
    check's findings — came from one file's 180,084 such rows. A finding
    resting on one of them is not a finding about the price list.
    """
    if number > len(rows):
        return False
    row = rows[number - 1]
    extent = 0
    for position, cell in enumerate(row):
        if cell.strip():
            extent = position + 1
    return extent <= len(header) and len(row) >= len(header)


def cell_by_label(header: list[str], row: list[str], label: str) -> str | None:
    for index, name in enumerate(header):
        if name.strip() == label.strip():
            return row[index].strip() if index < len(row) else ""
    return None


def audit_one_row(directory: Path, entry: dict) -> str:
    """Check that a single-row finding quotes numbers that are in that row.

    The finding names a row and prints the values it compared. This goes back
    to the row and confirms every number the finding quotes is a cell in it.
    That is not the same computation the check did — it is the question a
    person reading the audit wants answered, which is whether the finding
    describes the document.
    """
    path = directory / entry["file"]
    if not path.exists():
        return "missing file"
    found = ROW_IN_PLACE.search(entry["statement"]) or ROW_IN_PLACE.search(
        " ".join(entry["places"])
    )
    if not found:
        return "could not locate the row"
    number = int(found.group(1))
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        rows = list(csv.reader(handle))
    if number > len(rows):
        return "row beyond the file"
    header, _ = effective_header(rows)
    if header is not None and not row_is_well_formed(rows, header, number):
        # Never expected now — a ragged row is not read at all — so seeing it
        # means the row-width rule has a hole in it.
        return "RAGGED ROW: the cited row's cell count is not the header's"
    cells = {cell.strip() for cell in rows[number - 1]}
    quoted = set()
    for line in [entry["statement"], *entry["detail"]]:
        quoted.update(NUMBER.findall(line))
    # The row number itself, and any figure the finding computed rather than
    # read, are not expected to be cells.
    quoted.discard(str(number))
    present = [value for value in quoted if value in cells]
    return (
        "quotes the row" if len(present) >= 2
        else "fewer than two quoted values found in the row"
    )


def audit_arithmetic(directory: Path, entry: dict, check: str) -> str:
    """Re-derive a single-row finding from the raw cells it names.

    The finding prints its own arithmetic; this reads the columns it cites
    straight out of the file and does the sum again, which is the half of a
    hand audit a person should not be doing by eye over thirty findings.

    For ``stated-discount`` it reports which reading of the percentage column
    reconciles, because that is exactly what a hospital writing ``0.85`` for
    85% does to this check.
    """
    path = directory / entry["file"]
    if not path.exists():
        return "missing file"
    places = [PLACE.match(place) for place in entry["places"]]
    places = [match for match in places if match]
    if not places:
        return "could not locate the columns"
    number = int(places[0].group(1))
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        rows = list(csv.reader(handle))
    header, _ = effective_header(rows)
    if header is None:
        return "no header found"
    if not row_is_well_formed(rows, header, number):
        return "RAGGED ROW: the cited row's cell count is not the header's"
    row = rows[number - 1]
    values = []
    for match in places:
        cell = cell_by_label(header, row, match.group(2))
        if cell is None:
            return f"no column called {match.group(2)!r}"
        values.append(cell)
    try:
        numbers = [Decimal(value.replace(",", "").replace("%", "").strip())
                   for value in values]
    except (InvalidOperation, ValueError):
        return "a cited cell does not hold a number"

    if check == "inverted-range" and len(numbers) == 2:
        low, high = numbers
        return ("the row does state a minimum above its maximum"
                if low > high else "THE ROW DOES NOT: minimum is not above maximum")

    if check == "stated-discount" and len(numbers) == 3:
        gross, percent, net = numbers
        if gross == 0:
            return "the list price on that row is zero"
        as_printed = gross * percent / Decimal(100)
        as_fraction = gross * percent
        tolerance = abs(net) * Decimal("0.005") + Decimal("0.01")
        printed_ok = abs(as_printed - net) <= tolerance
        fraction_ok = abs(as_fraction - net) <= tolerance
        if printed_ok:
            return "RECONCILES as printed — the finding is wrong"
        if fraction_ok:
            return "reconciles only if the percentage column holds a fraction"
        return "reconciles under neither reading"
    return "not re-derivable from the columns it names"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("samples", type=Path)
    parser.add_argument("--check", help="audit only this check")
    parser.add_argument("--show", type=int, default=3, help="differing columns to print")
    args = parser.parse_args()

    drawn = json.loads(args.samples.read_text(encoding="utf-8"))["samples"]
    for name, entries in sorted(drawn.items()):
        if args.check and name != args.check:
            continue
        if name not in ("two-prices", "unit-mismatch"):
            print(f"\n=== {name}: {len(entries)} finding(s), single-row")
            verdicts: Counter = Counter()
            derived: Counter = Counter()
            for entry in entries:
                verdicts[audit_one_row(args.directory, entry)] += 1
                derived[audit_arithmetic(args.directory, entry, name)] += 1
            for verdict, count in verdicts.most_common():
                print(f"  {count:3}  {verdict}")
            print("  re-derived from the cited cells:")
            for verdict, count in derived.most_common():
                print(f"  {count:3}  {verdict}")
            for entry in entries[: args.show]:
                print(f"    {entry['file'][:40]}: {entry['statement'][:110]}")
            continue

        verdicts: Counter = Counter()
        print(f"\n=== {name}: {len(entries)} finding(s)")
        for entry in entries:
            path = args.directory / entry["file"]
            if not path.exists():
                verdicts["missing file"] += 1
                continue
            with path.open(newline="", encoding="utf-8", errors="replace") as handle:
                rows = list(csv.reader(handle))
            header, _ = header_of(rows)
            if header is None:
                verdicts["no header found"] += 1
                continue
            found = TWO_ROWS.search(entry["statement"])
            if found:
                first, second = int(found.group(1)), int(found.group(2))
            else:
                numbers = ROW_IN_PLACE.findall(" ".join(entry["places"]))
                if len(numbers) < 2:
                    verdicts["could not locate the rows"] += 1
                    continue
                first, second = int(numbers[0]), int(numbers[1])
            if max(first, second) > len(rows):
                verdicts["row beyond the file"] += 1
                continue
            trimmed, _ = effective_header(rows)
            if trimmed is not None and not all(
                row_is_well_formed(rows, trimmed, number) for number in (first, second)
            ):
                verdicts["RAGGED ROW: a cited row's cell count is not the header's"] += 1
                continue
            verdict, differ = audit_two_rows(rows, header, first, second, name)
            verdicts[verdict] += 1
            if verdict == "distinguished":
                shown = [(n[:40], a[:20], b[:20]) for n, a, b in differ[: args.show]]
                print(f"  distinguished  {entry['file'][:34]} rows {first}/{second}")
                for item in shown:
                    print(f"      {item}")
        for verdict, count in verdicts.most_common():
            print(f"  {count:3}  {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
