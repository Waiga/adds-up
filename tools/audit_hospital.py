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
            # The other checks are single-row statements: the finding quotes
            # both numbers it compared, so re-reading the row adds nothing a
            # reader cannot do from the finding itself.
            print(f"\n=== {name}: {len(entries)} finding(s), each a single row; "
                  "read the statement")
            for entry in entries[: args.show]:
                print(f"    {entry['file'][:44]}: {entry['statement'][:120]}")
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
