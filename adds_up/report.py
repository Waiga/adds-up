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


def text(result: Result, version: str) -> str:
    lines = [f"adds-up {version} — {result.path}", ""]
    for table in result.tables:
        if len(result.tables) > 1:
            lines.append(f"=== {table.sheet} ===")
        lines.append(
            f"{table.row_count} row(s) under a header read from {table.header_reason}."
        )
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
                    f"from {check.comparisons} comparison(s) "
                    if check.comparisons or check.name != "unit-mismatch" else ""
                )
                lines.append(
                    f"  ran      {check.name:<20} {len(check.findings)} finding(s) "
                    f"{counted}— {check.reason}"
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
            role = column.role or "—"
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
                f"{check.comparisons if check.ran else '—'} | "
                f"{len(check.findings) if check.ran else '—'} | {check.reason} |"
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
