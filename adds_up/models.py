"""What a run produces.

A finding is a statement about two numbers the document itself prints. It has
no severity, no score and no verdict, because this tool has no way to know
whether a price is meant to be what it is. ``statement`` is the whole content
of a finding and it is always of the form *this row says X and that row says
Y*.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Place:
    """Where in a file a value was printed."""

    sheet: str
    row: int
    column: str

    def __str__(self) -> str:
        return f"{self.sheet}!row {self.row}, {self.column}"


@dataclass(frozen=True)
class Finding:
    """One arithmetic contradiction, with the printed values behind it."""

    check: str
    statement: str
    places: tuple[Place, ...]
    detail: tuple[str, ...] = ()
    #: Set when a finding has a known, named reason to be read carefully. It
    #: is not a confidence score: it is a fact about the rows, printed so a
    #: reader can see it without opening the file.
    note: str = ""


@dataclass
class CheckRun:
    """Whether a check ran, and if not, exactly what was missing.

    A check that did not run is never allowed to read as a check that found
    nothing, which is why ``ran`` and ``findings`` are separate and why
    ``reason`` is mandatory when ``ran`` is false.
    """

    name: str
    ran: bool
    reason: str
    findings: list[Finding] = field(default_factory=list)
    #: Rows the check could see but deliberately did not judge, with why.
    set_aside: list[str] = field(default_factory=list)
    #: How many pairs of *numbers* this check actually compared.
    #:
    #: ``ran`` is not enough to earn a clean result. A check can find its
    #: columns, report ``ran``, and compare nothing — every row blank, or one
    #: row per group. And ``unit-mismatch`` compares text, never numbers, so a
    #: run in which only it did any work has done no arithmetic at all. Exit 0
    #: means "the arithmetic checks out", so it is gated on this, not on
    #: ``ran``: a review found that a price list with a real inverted tier in
    #: it exited 0 because the units matched.
    comparisons: int = 0


@dataclass
class TableResult:
    sheet: str
    header_row_number: int
    header_reason: str
    row_count: int
    columns: list  # list[columns.Column]
    conventions: dict  # index -> sentence
    #: The rows above the header, as text. A price list's title block often
    #: carries the currency, the effective date or the schema version that
    #: the columns themselves do not repeat.
    preamble: list = field(default_factory=list)
    checks: list[CheckRun] = field(default_factory=list)

    @property
    def findings(self) -> list[Finding]:
        return [f for check in self.checks for f in check.findings]


@dataclass
class Result:
    path: str
    tables: list[TableResult] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def findings(self) -> list[Finding]:
        return [f for table in self.tables for f in table.findings]

    @property
    def any_check_ran(self) -> bool:
        return any(check.ran for table in self.tables for check in table.checks)

    @property
    def comparisons(self) -> int:
        """Pairs of numbers actually compared, across every check and sheet."""
        return sum(
            check.comparisons for table in self.tables for check in table.checks
        )
