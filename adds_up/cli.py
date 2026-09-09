"""The command line.

Exit codes: ``0`` nothing found, ``1`` at least one finding, ``2`` could not
run. A file that did not parse exits 2, and so does a run in which **no two
numbers were compared** — whether because every check was switched off, or
because none could find its columns, or because the columns it found were
empty.

That gate is on comparisons and not on whether a check reported ``ran``,
because a review found the difference mattered. ``unit-mismatch`` needs no
numbers at all, so a price list with a real inverted tier in it, whose price
column had a heading this tool does not know, exited 0 on the strength of its
units matching. A green result over a price list nothing was compared in is
the one outcome this tool exists not to produce.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, report
from .analyse import analyse
from .checks import CHECK_DESCRIPTIONS, CHECK_NAMES
from .columns import ROLES, vocabulary_lines
from .tables import UnreadableFile

EPILOGUE = """
It reports arithmetic in a price list that contradicts itself. It never says a
price is right, wrong, competitive, fair or profitable, and it cannot: a price
list does not state a cost, so nothing here is about margin.
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="adds-up",
        description="Reads a price list and reports the arithmetic in it that "
                    "contradicts itself.",
        epilog=EPILOGUE,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("path", nargs="?", help="a .csv, .tsv or .xlsx price list")
    parser.add_argument("--version", action="version", version=f"adds-up {__version__}")
    parser.add_argument(
        "--format", choices=("text", "markdown", "json"), default="text"
    )
    parser.add_argument(
        "--skip", action="append", default=[], metavar="CHECK",
        help="switch off one check; repeatable",
    )
    parser.add_argument("--sheet", help="read only this worksheet of a workbook")
    parser.add_argument(
        "--header-row", type=int, metavar="N",
        help="the header is on row N, counting from 1",
    )
    parser.add_argument(
        "--map", action="append", default=[], metavar="COLUMN=ROLE",
        help="say what a column is: --map 3=unit_price, or --map 'List £'=list_price",
    )
    parser.add_argument(
        "--list-checks", action="store_true", help="print the checks and exit"
    )
    parser.add_argument(
        "--list-columns", action="store_true",
        help="print every column name this tool recognises, and exit",
    )
    return parser


def _parse_map(entries: list[str], header: list[str]) -> dict[int, str]:
    out: dict[int, str] = {}
    for entry in entries:
        if "=" not in entry:
            raise ValueError(f"--map wants COLUMN=ROLE, not {entry!r}")
        left, role = entry.rsplit("=", 1)
        role = role.strip()
        if role not in ROLES:
            raise ValueError(
                f"--map {entry!r}: {role!r} is not a role. They are: {', '.join(ROLES)}"
            )
        left = left.strip()
        if left.isdigit():
            index = int(left) - 1
        else:
            folded = [name.strip().casefold() for name in header]
            if left.casefold() not in folded:
                raise ValueError(
                    f"--map {entry!r}: no column is called {left!r}. "
                    f"The columns are: {', '.join(repr(n) for n in header)}"
                )
            index = folded.index(left.casefold())
        out[index] = role
    return out


def _header_of(path: Path, sheet, header_row) -> list[str]:
    from . import tables

    return tables.read(path, sheet=sheet, header_row=header_row)[0].header


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list_checks:
        for name in CHECK_NAMES:
            print(f"{name}\n    {CHECK_DESCRIPTIONS[name]}")
        return 0
    if args.list_columns:
        for line in vocabulary_lines():
            print(line)
        return 0
    if not args.path:
        parser.print_usage(sys.stderr)
        print("adds-up: a file to read is required", file=sys.stderr)
        return 2

    unknown = [name for name in args.skip if name not in CHECK_NAMES]
    if unknown:
        print(
            f"adds-up: no check is called {unknown[0]!r}. They are: "
            f"{', '.join(CHECK_NAMES)}",
            file=sys.stderr,
        )
        return 2

    path = Path(args.path)
    if not path.exists():
        print(f"adds-up: {path} does not exist", file=sys.stderr)
        return 2

    try:
        overrides = {}
        if args.map:
            overrides = _parse_map(args.map, _header_of(path, args.sheet, args.header_row))
        result = analyse(
            path,
            skip=set(args.skip),
            sheet=args.sheet,
            header_row=args.header_row,
            overrides=overrides,
        )
    except UnreadableFile as error:
        print(f"adds-up: {error}", file=sys.stderr)
        return 2
    except ValueError as error:
        print(f"adds-up: {error}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(report.as_json(result, __version__))
    elif args.format == "markdown":
        print(report.markdown(result, __version__))
    else:
        print(report.text(result, __version__), end="")

    if result.comparisons == 0:
        ran = [c.name for t in result.tables for c in t.checks if c.ran]
        print(
            "adds-up: no two numbers were compared, so this is not a clean "
            "result. "
            + (
                f"{len(ran)} check(s) reported that they ran, but none of them "
                "did any arithmetic. "
                if ran else ""
            )
            + "See the CHECKS block for what each one was looking for.",
            file=sys.stderr,
        )
        return 2
    return 1 if result.findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
