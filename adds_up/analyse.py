"""Putting a run together: read the file, name the columns, run the checks."""

from __future__ import annotations

from pathlib import Path

from . import checks as check_module
from . import tables
from .columns import classify
from .models import Result, TableResult
from .numbers import convention_of


def _conventions(table: tables.Table, columns) -> tuple[dict, dict]:
    """Decide, per column, how to read the separators in it.

    Only columns a check might do arithmetic on are decided, because deciding
    the convention of a description column is meaningless and its explanation
    would be noise in the report.
    """
    numeric_roles = {
        "quantity", "unit_price", "list_price", "net_price",
        "discount_percent", "percent_of_list", "adjustment",
        "minimum", "maximum",
    }
    conventions: dict[int, object] = {}
    reasons: dict[int, str] = {}
    for column in columns:
        if column.role not in numeric_roles:
            continue
        convention, reason = convention_of(table.column(column.index))
        conventions[column.index] = convention
        reasons[column.index] = reason
    return conventions, reasons


def analyse(
    path: Path,
    skip: set[str] | None = None,
    sheet: str | None = None,
    header_row: int | None = None,
    overrides: dict[int, str] | None = None,
) -> Result:
    skip = skip or set()
    result = Result(path=str(path))

    def names_recognised(row: list[str]) -> int:
        """How many of a candidate header row's labels this tool has a name for.

        This is what settles a file with both a title block above the header
        and a sub-header below it. It reads names, never contents, so it does
        not weaken the rule that a column's role comes from what it is called.
        """
        return sum(1 for column in classify(row, overrides) if column.role)

    for table in tables.read(
        path, sheet=sheet, header_row=header_row, score=names_recognised
    ):
        columns = classify(table.header, overrides)
        conventions, reasons = _conventions(table, columns)
        table_result = TableResult(
            sheet=table.name,
            header_row_number=table.header_row_number,
            header_reason=table.header_reason,
            row_count=len(table.rows),
            columns=columns,
            conventions=reasons,
        )
        reader = check_module.Reader(
            sheet=table.name,
            header=table.header,
            rows=table.rows,
            columns=columns,
            conventions=conventions,
            header_row_number=table.header_row_number,
            reasons=reasons,
        )
        for name in check_module.CHECK_NAMES:
            if name in skip:
                table_result.checks.append(
                    check_module.CheckRun(name, False, "switched off with --skip")
                )
                continue
            table_result.checks.append(check_module.RUNNERS[name](reader))
        result.tables.append(table_result)
    return result
