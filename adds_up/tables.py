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

    ``slots=True`` is not a micro-optimisation here. The largest published
    file in the reference corpus is 93,954 rows of 285 columns, which is 26.8
    million of these; without slots each one carries a dictionary of its own
    and the file needs several gigabytes more to open. The memory this still
    costs is measured and published in the README, because it is the tool's
    hardest limit.
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
    #: The line each kept row was printed on, counting from 1. Rows are
    #: dropped — a blank one, a ragged one — so a row's position in ``rows``
    #: is not its position in the file, and a finding must cite the file.
    row_numbers: list[int] = field(default_factory=list)
    #: Rows not read because their cell count does not match the header's.
    #: Counted in both directions and reported, never silently discarded.
    wider_than_header: int = 0
    narrower_than_header: int = 0

    @property
    def set_aside_for_width(self) -> int:
        return self.wider_than_header + self.narrower_than_header

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
    Taking the last candidate handles that, and it is what almost every file
    in the hospital corpus needs; the measurement reports the distribution of
    the rows actually chosen.

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
        f"row {best + 1}, the only header-shaped row above the data with data "
        f"under it; {best} row(s) above it were read as a title block"
        if len(candidates) == 1 else
        f"row {best + 1}, the last of {len(candidates)} header-shaped row(s); "
        f"{best} row(s) above it were read as a title block"
    )


#: How large a single cell may be. ``csv`` defaults to 128 kB and raises on
#: anything larger, which killed three of the 200 files in the reference
#: corpus outright: a hospital's footnote column holds paragraphs. The limit
#: is raised around the read and put back afterwards, because it is a
#: process-wide setting and a library has no business leaving it changed.
LARGEST_CELL = 16 * 1024 * 1024


#: A JSON document does not become a table by being named ``.csv``, and 27 of
#: the 200 files in the reference corpus are exactly that: the CMS schema's
#: JSON form served from a URL ending ``.csv``. Read as delimited text one of
#: them is a single row of up to 1.16 million fields. No check could ever find
#: a column it could use, so the run already ended in exit 2 and invented
#: nothing — but it never said *this is not a table*, and a reader had to
#: infer it from a header a million columns wide.
_JSON_KEY = re.compile(rb'"\s*:')


def _looks_like_json(path: Path) -> bool:
    with path.open("rb") as handle:
        head = handle.read(65536)
    stripped = head.lstrip(b"\xef\xbb\xbf").lstrip()
    if stripped[:1] not in (b"{", b"["):
        return False
    # A bare bracket is not enough: a price list may open with one. A JSON
    # object's first key is, and every form of the CMS JSON schema has one
    # within the first block of the file.
    return _JSON_KEY.search(stripped[:65536]) is not None


def _read_csv_grid(path: Path) -> list[list[str]]:
    if _looks_like_json(path):
        raise UnreadableFile(
            f"{path.name} is a JSON document, not a table. It is named like a "
            "CSV and it does not hold rows and columns, so there is nothing "
            "here for this tool to read. (Published price files are served "
            "this way more often than the file name suggests.)"
        )
    previous = csv.field_size_limit()
    try:
        csv.field_size_limit(LARGEST_CELL)
        with path.open("r", newline="", encoding="utf-8-sig", errors="replace") as handle:
            sample = handle.read(65536)
            handle.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            except csv.Error:
                dialect = csv.excel
            try:
                return [list(row) for row in csv.reader(handle, dialect)]
            except csv.Error as error:
                raise UnreadableFile(
                    f"{path.name} could not be read as delimited text: {error}"
                ) from error
    finally:
        csv.field_size_limit(previous)


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
            available = [name for name, _ in _sheet_targets(archive)]
            if sheet and sheet not in available:
                raise UnreadableFile(
                    f"{path.name} has no worksheet called {sheet!r}. It has: "
                    + ", ".join(repr(name) for name in available)
                )
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
                tables.append(
                    _assemble(name, grid, header_row, score, positional=True)
                )
            if not tables:
                raise UnreadableFile(f"{path.name} holds no readable worksheet")
            return tables
    raise UnreadableFile(
        f"{path.name}: this tool reads .csv, .tsv and .xlsx. It does not read "
        f"'{suffix or 'files without a suffix'}'."
    )


def _assemble(
    name: str,
    grid: list[list[Cell]],
    header_row: int | None,
    score=None,
    positional: bool = False,
) -> Table:
    """Cut a grid into a header and the rows under it.

    ``positional`` says that a cell's place in its row is stated by the file
    rather than counted from the delimiters. That is true of an .xlsx, where
    every cell carries its own column reference, and false of a CSV, where a
    single unquoted comma inside a free-text field shifts every value after it
    into the wrong column.

    So in delimited text **a row whose cell count is not the header line's is
    not read**. Its values are under headings that are not theirs, and a value
    that cannot be trusted must not become a finding; the count of what was
    set aside is reported instead, which is the part that used to be silent.
    One published standard-charges file carries 180,084 such rows out of
    1,342,453, and every one of its 1,517 inverted ranges was one of them.

    A row with a cell too many is not saved by that cell being blank. An
    unquoted comma splits one field into two and pushes every field after it
    one place right, so the cell that falls off the end holds whatever the
    last column held — often nothing. Reading such a row because its tail
    looks empty leaves the shift in the middle of it untouched, which is
    exactly the defect this rule exists to stop.
    """
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
    width = len(header)
    # A header line can end in commas, and what follows them is a column with
    # no name — which no check can use, but which a data row may still fill.
    # Two published files disagree about which happens: one has 25 headings
    # with the last empty above 1,444,617 rows of 24 cells, and another has
    # 24 headings with the last three empty above 27,356 rows of 24 cells
    # that put a value in the last one. So a row is judged against both ends:
    # it may not have more cells than the header line, and it must reach
    # every heading that has a name.
    named = 0
    for position, label in enumerate(header):
        if not _blank(label):
            named = position + 1
    rows: list[list[Cell]] = []
    row_numbers: list[int] = []
    wider = narrower = 0
    for offset, row in enumerate(grid[index + 1:]):
        count = len(row)
        if not positional and (count > width or count < named):
            # A blank row is a blank row whatever its width; only a row with
            # something in it is a row that was not read.
            if any(not _blank(cell.text) for cell in row):
                if count > width:
                    wider += 1
                else:
                    narrower += 1
            continue
        if not any(not _blank(c.text) for c in row[:width] or row):
            continue
        rows.append(row)
        row_numbers.append(index + 2 + offset)
    return Table(
        name=name,
        header=header,
        rows=rows,
        header_row_number=index + 1,
        header_reason=reason,
        total_rows=len(grid),
        preamble=[row for row in text_grid[:index]],
        row_numbers=row_numbers,
        wider_than_header=wider,
        narrower_than_header=narrower,
    )
