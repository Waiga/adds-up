"""Printing a result.

The shape of the report is the argument the tool is making. A check that did
not run appears in the same list, at the same size, as a check that ran and
found nothing, because those are two different answers and a reader who
cannot tell them apart has been misled.
"""

from __future__ import annotations

import json

from .checks import CHECK_DESCRIPTIONS
from .models import Result

WIDTH = 74


def _rule(character: str = "-") -> str:
    return character * WIDTH


def _width_lines(table) -> list[str]:
    """What was set aside because its cell count was not the header's.

    Silence here is the failure this reports. A row wider than the header has
    a value under a heading that is not its own — an unquoted comma inside a
    free-text field does it — and every check then reads the wrong column
    without saying so. It was the largest measured source of wrong findings in
    this tool's whole history, and there was no line in the report about it.
    """
    if not table.rows_set_aside_for_width:
        return []
    parts = []
    if table.rows_wider_than_header:
        parts.append(f"{table.rows_wider_than_header} with more cells than that")
    if table.rows_narrower_than_header:
        parts.append(f"{table.rows_narrower_than_header} not reaching every named column")
    return [
        f"{table.rows_set_aside_for_width} further row(s) were NOT read: they do "
        f"not fit the {table.header_width} cell(s) on the header line "
        f"({'; '.join(parts)}). The values in a row of the wrong width sit under "
        "headings that are not theirs, so nothing in this report comes from them."
    ]


def text(result: Result, version: str) -> str:
    lines = [f"adds-up {version}: {result.path}", ""]
    for table in result.tables:
        if len(result.tables) > 1:
            lines.append(f"=== {table.sheet} ===")
        lines.append(
            f"{table.row_count} row(s) under a header read from {table.header_reason}."
        )
        for line in _width_lines(table):
            lines.append(line)
        named = [c for c in table.columns if c.role]
        lines.append(
            f"{len(named)} of {len(table.columns)} column(s) were given a role."
        )
        ran = [c for c in table.checks if c.ran]
        found = sum(len(c.findings) for c in table.checks)
        compared = sum(c.comparisons for c in table.checks)
        lines.append(
            f"{len(ran)} of {len(table.checks)} check(s) ran, comparing "
            f"{compared} pair(s) of numbers. {found} finding(s)."
        )
        lines.append("")

        for check in table.checks:
            if not check.findings:
                continue
            lines.append(check.name.upper())
            lines.append(f"  {CHECK_DESCRIPTIONS[check.name]}")
            lines.append("")
            for finding in check.findings:
                lines.append(f"  {finding.statement}")
                for line in finding.detail:
                    lines.append(f"      {line}")
                if finding.note:
                    lines.append(f"      note: {finding.note}")
                lines.append(f"      at {', '.join(str(p) for p in finding.places)}")
                lines.append("")

        lines.append("CHECKS")
        for check in table.checks:
            if check.ran:
                counted = (
                    f" from {check.comparisons} comparison(s)"
                    if check.comparisons or check.name != "unit-mismatch" else ""
                )
                lines.append(
                    f"  ran      {check.name:<20} {len(check.findings)} finding(s)"
                    f"{counted}: {check.reason}"
                )
            else:
                lines.append(f"  DID NOT RUN {check.name:<17} {check.reason}")
        lines.append("")
        lines.append(
            "  A check that did not run has found nothing because it was not made."
        )
        lines.append("")

        aside = [(c.name, line) for c in table.checks for line in c.set_aside]
        if aside:
            lines.append("SEEN AND NOT JUDGED")
            for name, line in aside:
                lines.append(f"  {name}: {line}")
            lines.append("")

        lines.append("COLUMNS")
        for column in table.columns:
            role = column.role or "no role"
            lines.append(f"  {column.label!r:<34} {role:<18} {column.reason}")
            if column.index in table.conventions and column.role:
                lines.append(f"  {'':<34} {'':<18} numbers: {table.conventions[column.index]}")
        lines.append("")

    if not result.findings:
        lines.append(
            "Nothing in what was checked contradicts itself. That is a statement "
            "about the checks that ran, listed above, and about nothing else."
        )
        lines.append("")
    return "\n".join(lines)


def markdown(result: Result, version: str) -> str:
    lines = [f"# adds-up {version}", "", f"`{result.path}`", ""]
    for table in result.tables:
        lines.append(f"## {table.sheet}")
        lines.append("")
        lines.append(
            f"{table.row_count} row(s); header read from {table.header_reason}."
        )
        for line in _width_lines(table):
            lines.append("")
            lines.append(f"**{line}**")
        lines.append("")
        for check in table.checks:
            if not check.findings:
                continue
            lines.append(f"### {check.name}")
            lines.append("")
            lines.append(f"_{CHECK_DESCRIPTIONS[check.name]}_")
            lines.append("")
            for finding in check.findings:
                lines.append(f"- {finding.statement}")
                for line in finding.detail:
                    lines.append(f"    - {line}")
                if finding.note:
                    lines.append(f"    - _note: {finding.note}_")
                lines.append(
                    f"    - at {', '.join(str(p) for p in finding.places)}"
                )
            lines.append("")
        lines.append("### Which checks ran")
        lines.append("")
        lines.append("| check | ran | comparisons | findings | why |")
        lines.append("|---|---|---|---|---|")
        for check in table.checks:
            lines.append(
                f"| {check.name} | {'yes' if check.ran else '**no**'} | "
                f"{check.comparisons if check.ran else 'not run'} | "
                f"{len(check.findings) if check.ran else 'not run'} | {check.reason} |"
            )
        lines.append("")
        lines.append("A check that did not run has found nothing because it was not made.")
        lines.append("")
    return "\n".join(lines)


def as_json(result: Result, version: str) -> str:
    payload = {
        "tool": "adds-up",
        "version": version,
        "path": result.path,
        "tables": [
            {
                "sheet": table.sheet,
                "header_row": table.header_row_number,
                "header_reason": table.header_reason,
                "rows": table.row_count,
                "header_width": table.header_width,
                "rows_not_read_wider_than_header": table.rows_wider_than_header,
                "rows_not_read_narrower_than_header": table.rows_narrower_than_header,
                "columns": [
                    {
                        "index": column.index,
                        "name": column.name,
                        "role": column.role,
                        "reason": column.reason,
                        "family": column.family,
                        "candidates": list(column.candidates),
                        "number_convention": table.conventions.get(column.index),
                    }
                    for column in table.columns
                ],
                "checks": [
                    {
                        "name": check.name,
                        "ran": check.ran,
                        "reason": check.reason,
                        "comparisons": check.comparisons,
                        "set_aside": check.set_aside,
                        "findings": [
                            {
                                "check": finding.check,
                                "statement": finding.statement,
                                "detail": list(finding.detail),
                                "note": finding.note,
                                "places": [
                                    {
                                        "sheet": place.sheet,
                                        "row": place.row,
                                        "column": place.column,
                                    }
                                    for place in finding.places
                                ],
                            }
                            for finding in check.findings
                        ],
                    }
                    for check in table.checks
                ],
            }
            for table in result.tables
        ],
    }
    return json.dumps(payload, indent=2)
