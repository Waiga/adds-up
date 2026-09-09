"""Reading a price list out of a CSV or an XLSX, without leaving the machine.

Only two things are wanted from a file: the text each cell prints, and how
many decimal places it prints. A CSV gives both for free, because a CSV cell
*is* its printed text. An XLSX does not: it stores ``12.34`` as a number and
its appearance somewhere else entirely, so the decimals have to be recovered
from the cell's number format or the tolerance in every comparison would be
wrong.

The XLSX reader is ``zipfile`` and ``xml.etree`` and nothing else. An .xlsx is
a zip of XML, only values are needed, and a dependency in the install is a
dependency the offline test cannot read.
"""

from __future__ import annotations

import csv
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree

from .numbers import BLANKS

MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RELS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PACKAGE_RELS = "{http://schemas.openxmlformats.org/package/2006/relationships}"

#: How far down a file the header row is looked for. A price list that buries
#: its header below this has to be told where it is with ``--header-row``.
HEADER_SEARCH_DEPTH = 25

#: Built-in Excel number formats that carry decimals, by format id. The rest of
#: the built-ins are integers, dates or text, all of which mean zero decimals
#: for this purpose.
BUILTIN_DECIMALS = {
    2: 2, 4: 2, 7: 2, 8: 2, 10: 2, 11: 2, 39: 2, 40: 2, 43: 2, 44: 2,
}

#: The largest a single part of an .xlsx may declare itself to be once
#: unpacked. An .xlsx is a zip, a zip can claim to hold far more than it does,
#: and this tool reads files people were sent rather than files they wrote. A
#: real worksheet part of a gigabyte is already past what the tool can hold in
#: memory, so refusing at that point costs nothing and closes the hole.
LARGEST_PART = 1 << 30

_CELL_REF = re.compile(r"^([A-Z]+)(\d+)$")


class UnreadableFile(Exception):
    """The file could not be read as a table at all."""


def _part(archive: zipfile.ZipFile, name: str) -> bytes:
    """Read one part of a workbook, refusing two things before parsing it.

    **A part that claims to unpack to more than a gigabyte.** A zip's headers
    are self-declared, so a few kilobytes can claim to be a terabyte; reading
    it is how a tool gets killed by a file somebody emailed.

    **A part that declares an XML document type.** ``xml.etree`` expands
    internal entities, so a DOCTYPE with a nested entity is the billion-laughs
    attack and needs no external network access to work. No legitimate part of
    an .xlsx carries one, so the presence of the declaration is enough to
    refuse — which is a blunter rule than disabling the handler, and a rule
    that cannot be got round by a handler being reattached.
    """
    try:
        info = archive.getinfo(name)
    except KeyError as error:
        raise KeyError(name) from error
    if info.file_size > LARGEST_PART:
        raise UnreadableFile(
            f"{name} in this .xlsx declares itself to be "
            f"{info.file_size / (1 << 20):.0f} MB once unpacked, which this tool "
            "will not read"
        )
    try:
        data = archive.read(name)
    except Exception as error:  # noqa: BLE001
        # Deliberately broad, and only around this one call. A zip's CRC is
        # checked when a part is decompressed, not when the archive is opened,
        # so a truncated or corrupted upload fails here and not earlier — and
        # it fails with `zlib.error`, which is neither an `OSError` nor a
        # `zipfile.BadZipFile`. Catching the two obvious types left a
        # traceback and exit 1, the code that means findings were reported.
        # Every way of failing to unpack a part means the same thing to a
        # reader: this file cannot be read.
        raise UnreadableFile(
            f"{name} in this .xlsx could not be unpacked: "
            f"{type(error).__name__}: {error}"
        ) from error
    head = data[:4096].lstrip()
    if b"<!DOCTYPE" in head or b"<!ENTITY" in data[:65536]:
        raise UnreadableFile(
            f"{name} in this .xlsx declares an XML document type. No part of a "
            "spreadsheet needs one, and expanding it is how a small file "
            "becomes an unbounded one, so it is refused."
        )
    return data


@dataclass(slots=True)
class Cell:
    """One cell's printed text, and how many decimals that printing showed.

    ``decimals`` is ``None`` when nothing is known about the formatting, which
    is the honest answer for a CSV: its text is its format.

    ``slots=True`` is not a micro-optimisation here. A price list read from a
    published hospital file is 300,000 rows of 25 columns, which is 7.5 million
    of these; without slots each one carries a dictionary and the file needs
    several gigabytes to open. The memory this still costs is measured and
    published in the README, because it is the tool's hardest limit.
    """

    text: str
    format_decimals: int | None = None


@dataclass
class Table:
    """A sheet, its chosen header row, and the rows under it."""

    name: str
    header: list[str]
    rows: list[list[Cell]]
    header_row_number: int
    header_reason: str
    total_rows: int
    #: Rows above the header, kept because a price list's title block often
    #: carries the currency or the unit the columns do not repeat.
    preamble: list[list[str]] = field(default_factory=list)

    def column(self, index: int) -> list[str]:
        return [row[index].text if index < len(row) else "" for row in self.rows]

    def cells(self, index: int) -> list[Cell]:
        return [row[index] if index < len(row) else Cell("") for row in self.rows]


def _blank(text: str) -> bool:
    return str(text).strip().lower() in BLANKS


def _looks_like_a_header(row: list[str]) -> bool:
    """A header row names things; it does not price them.

    Two or more distinct non-blank labels, none of which is entirely a number.
    A row of prices fails on the last condition, which is the whole point.
    """
    filled = [c.strip() for c in row if not _blank(c)]
    if len(filled) < 2:
        return False
    if len(set(label.casefold() for label in filled)) != len(filled):
        return False
    for label in filled:
        stripped = label.replace(",", "").replace(".", "").replace(" ", "")
        stripped = stripped.lstrip("+-$€£").rstrip("%")
        if stripped.isdigit():
            return False
    return True


def find_header(grid: list[list[str]], score=None) -> tuple[int, str]:
    """Choose the header row, and say why in a sentence the report can print.

    Two shapes fight over this slot and neither can be told from the other by
    looking at one row.

    A published file often has a **title block above** the header — the CMS
    standard-charges template puts metadata names on row 1, metadata values on
    row 2 and the real column names on row 3, and all three look like headers.
    Taking the last candidate handles that, and it is what 95 of 99 files in
    the reference corpus need.

    But a price list just as often has a **sub-header below** — a units row, a
    category banner, a second language — and there the last candidate is the
    wrong one. A review demonstrated it stealing the slot from the real
    header.

    So when a ``score`` is given, the candidate that names the most things
    wins, and the last candidate only breaks a tie. The score is still a
    function of *names*: it is the column vocabulary, applied to the row.
    """
    candidates = []
    depth = min(len(grid), HEADER_SEARCH_DEPTH)
    for index in range(depth):
        if not _looks_like_a_header(grid[index]):
            continue
        following = grid[index + 1: index + 4]
        if not any(sum(1 for c in row if not _blank(c)) >= 2 for row in following):
            continue
        candidates.append(index)
    if not candidates:
        return 0, (
            "no row in the first "
            f"{depth} looked like a header, so the first row was used as one"
        )
    if score is None:
        best = candidates[-1]
    else:
        scored = [(score(grid[index]), index) for index in candidates]
        best = max(scored)[1]
        if len(candidates) > 1 and max(scored)[0] > 0:
            return best, (
                f"row {best + 1}, of {len(candidates)} header-shaped row(s) in "
                f"the first {depth}, because it names the most columns this "
                f"tool recognises ({max(scored)[0]})"
            )
    if best == 0:
        return 0, "the first row"
    return best, (
        f"row {best + 1}, the last header-shaped row above the data; "
        f"{best} row(s) above it were read as a title block"
    )


def _read_csv_grid(path: Path) -> list[list[str]]:
    with path.open("r", newline="", encoding="utf-8-sig", errors="replace") as handle:
        sample = handle.read(65536)
        handle.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        return [list(row) for row in csv.reader(handle, dialect)]


def _column_index(reference: str) -> int:
    match = _CELL_REF.match(reference)
    if not match:
        return -1
    letters = match.group(1)
    index = 0
    for character in letters:
        index = index * 26 + (ord(character) - 64)
    return index - 1


def _format_decimals(code: str) -> int:
    """How many decimal places a number format shows.

    Only the fraction part is counted, and only the placeholders in it. A
    format's currency literals and its thousands separators say nothing about
    precision.
    """
    if not code:
        return 0
    code = code.split(";")[0]
    code = re.sub(r'"[^"]*"', "", code)
    code = re.sub(r"\\.", "", code)
    if "." not in code:
        return 0
    fraction = code.rsplit(".", 1)[1]
    return len(re.findall(r"[0#?]", fraction))


def _styles(archive: zipfile.ZipFile) -> list[int | None]:
    """Decimal places per cell-format index, or ``None`` where unknown."""
    try:
        root = ElementTree.fromstring(_part(archive, "xl/styles.xml"))
    except (KeyError, ElementTree.ParseError):
        return []
    custom: dict[int, str] = {}
    for element in root.iter(f"{MAIN}numFmt"):
        try:
            custom[int(element.get("numFmtId", "-1"))] = element.get("formatCode", "")
        except ValueError:
            continue
    out: list[int | None] = []
    container = root.find(f"{MAIN}cellXfs")
    if container is None:
        return []
    for entry in container.findall(f"{MAIN}xf"):
        try:
            format_id = int(entry.get("numFmtId", "0"))
        except ValueError:
            out.append(None)
            continue
        if format_id in custom:
            out.append(_format_decimals(custom[format_id]))
        elif format_id in BUILTIN_DECIMALS:
            out.append(BUILTIN_DECIMALS[format_id])
        elif format_id == 0:
            out.append(None)
        else:
            out.append(0)
    return out


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ElementTree.fromstring(_part(archive, "xl/sharedStrings.xml"))
    except (KeyError, ElementTree.ParseError):
        return []
    strings = []
    for item in root.findall(f"{MAIN}si"):
        strings.append("".join(node.text or "" for node in item.iter(f"{MAIN}t")))
    return strings


def _sheet_targets(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
    """The worksheets a workbook declares, or nothing if it declares none.

    A zip that is not a workbook, or a workbook whose parts have been stripped,
    raises out of ``zipfile`` and ``ElementTree`` in ways that have nothing to
    do with price lists. Both are turned into "this is not a readable .xlsx" by
    the caller.
    """
    try:
        root = ElementTree.fromstring(_part(archive, "xl/workbook.xml"))
        rels = ElementTree.fromstring(_part(archive, "xl/_rels/workbook.xml.rels"))
    except (KeyError, ElementTree.ParseError):
        return []
    targets = {
        rel.get("Id"): rel.get("Target", "")
        for rel in rels.findall(f"{PACKAGE_RELS}Relationship")
    }
    out = []
    sheets = root.find(f"{MAIN}sheets")
    if sheets is None:
        return []
    for sheet in sheets.findall(f"{MAIN}sheet"):
        target = targets.get(sheet.get(f"{RELS}id", ""), "")
        if not target:
            continue
        if not target.startswith("/"):
            target = "xl/" + target.lstrip("/")
        out.append((sheet.get("name", "sheet"), target.lstrip("/")))
    return out


def _read_xlsx_sheet(
    archive: zipfile.ZipFile, target: str, strings: list[str], styles: list[int | None]
) -> list[list[Cell]]:
    grid: list[list[Cell]] = []
    try:
        data = _part(archive, target)
    except KeyError:
        return grid
    root = ElementTree.fromstring(data)
    for row in root.iter(f"{MAIN}row"):
        cells: list[Cell] = []
        for cell in row.findall(f"{MAIN}c"):
            index = _column_index(cell.get("r", ""))
            if index < 0:
                index = len(cells)
            while len(cells) < index:
                cells.append(Cell(""))
            kind = cell.get("t", "n")
            if kind == "inlineStr":
                text = "".join(n.text or "" for n in cell.iter(f"{MAIN}t"))
            else:
                node = cell.find(f"{MAIN}v")
                text = node.text or "" if node is not None else ""
                if kind == "s":
                    try:
                        text = strings[int(text)]
                    except (ValueError, IndexError):
                        text = ""
            decimals = None
            if kind not in ("s", "inlineStr", "str"):
                try:
                    decimals = styles[int(cell.get("s", "0"))]
                except (ValueError, IndexError):
                    decimals = None
            cells.append(Cell(text, decimals))
        grid.append(cells)
    return grid


def read(
    path: Path,
    sheet: str | None = None,
    header_row: int | None = None,
    score=None,
) -> list[Table]:
    """Read every table a file offers.

    A CSV is one table. A workbook is one per worksheet, because a price list
    routinely puts each product family on its own tab and a contradiction
    inside one of them is still a contradiction.
    """
    suffix = path.suffix.lower()
    if suffix in (".csv", ".tsv", ".txt"):
        grid = _read_csv_grid(path)
        return [
            _assemble(
                path.name, [[Cell(c) for c in row] for row in grid], header_row, score
            )
        ]
    if suffix in (".xlsx", ".xlsm"):
        try:
            archive = zipfile.ZipFile(path)
        except zipfile.BadZipFile as error:
            raise UnreadableFile(f"{path.name} is not a readable .xlsx: {error}") from error
        with archive:
            strings = _shared_strings(archive)
            styles = _styles(archive)
            tables = []
            for name, target in _sheet_targets(archive):
                if sheet and name != sheet:
                    continue
                try:
                    grid = _read_xlsx_sheet(archive, target, strings, styles)
                except ElementTree.ParseError as error:
                    raise UnreadableFile(
                        f"{path.name}: worksheet {name!r} is not readable XML: {error}"
                    ) from error
                if not grid:
                    continue
                tables.append(_assemble(name, grid, header_row, score))
            if not tables:
                raise UnreadableFile(f"{path.name} holds no readable worksheet")
            return tables
    raise UnreadableFile(
        f"{path.name}: this tool reads .csv, .tsv and .xlsx. It does not read "
        f"'{suffix or 'files without a suffix'}'."
    )


def _assemble(
    name: str, grid: list[list[Cell]], header_row: int | None, score=None
) -> Table:
    if not grid:
        raise UnreadableFile(f"{name} is empty")
    text_grid = [[cell.text for cell in row] for row in grid]
    if header_row is not None:
        index = header_row - 1
        if index < 0 or index >= len(grid):
            raise UnreadableFile(
                f"{name}: --header-row {header_row} is outside the {len(grid)} row(s) in it"
            )
        reason = f"row {header_row}, because --header-row said so"
    else:
        index, reason = find_header(text_grid, score)
    header = [cell.strip() for cell in text_grid[index]]
    body = grid[index + 1:]
    width = len(header)
    rows = [row for row in body if any(not _blank(c.text) for c in row[:width] or row)]
    return Table(
        name=name,
        header=header,
        rows=rows,
        header_row_number=index + 1,
        header_reason=reason,
        total_rows=len(grid),
        preamble=[row for row in text_grid[:index]],
    )
