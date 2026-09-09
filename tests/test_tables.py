"""Getting a table, and a header row, out of a file."""

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))

from adds_up import tables as tables_module  # noqa: E402
from adds_up.tables import UnreadableFile, _format_decimals, find_header, read  # noqa: E402
from make_examples import write_xlsx  # noqa: E402


def temp(name: str, text: str) -> Path:
    directory = Path(tempfile.mkdtemp())
    path = directory / name
    path.write_text(text, encoding="utf-8")
    return path


class HeaderRow(unittest.TestCase):
    def test_the_first_row_when_the_first_row_is_the_header(self):
        index, why = find_header([["SKU", "Price"], ["A", "1.00"]])
        self.assertEqual(index, 0)

    def test_a_title_block_above_the_header_is_stepped_over(self):
        grid = [
            ["Acme trade price list"],
            ["effective 1 October"],
            [],
            ["SKU", "Quantity", "Price"],
            ["A", "1", "10.00"],
        ]
        index, why = find_header(grid)
        self.assertEqual(index, 3)
        self.assertIn("title block", why)

    def test_a_row_of_numbers_is_not_a_header(self):
        grid = [["1", "2"], ["SKU", "Price"], ["A", "1.00"]]
        index, _ = find_header(grid)
        self.assertEqual(index, 1)

    def test_a_row_with_a_repeated_label_is_not_a_header(self):
        grid = [["Price", "Price"], ["SKU", "Price"], ["A", "1.00"]]
        index, _ = find_header(grid)
        self.assertEqual(index, 1)

    def test_a_header_with_nothing_under_it_is_not_chosen(self):
        grid = [["SKU", "Price"], ["A", "1.00"], ["Notes", "Contact"]]
        index, _ = find_header(grid)
        self.assertEqual(index, 0)

    def test_a_sub_header_below_the_real_one_does_not_steal_the_slot(self):
        """A units row or a category banner is header-shaped too.

        Before the scorer, the last header-shaped row won unconditionally and
        this file's real header was demoted to a title block.
        """
        grid = [
            ["SKU", "Quantity", "Unit price"],
            ["Standard range", "Bulk range", "Notes"],
            ["W-1", "1", "9.00"],
            ["W-1", "1000", "50.00"],
        ]
        known = {"sku", "quantity", "unit price"}
        score = lambda row: sum(1 for c in row if c.strip().casefold() in known)
        index, why = find_header(grid, score)
        self.assertEqual(index, 0)
        self.assertIn("names the most columns", why)

    def test_a_title_block_above_still_wins_when_it_names_less(self):
        """The published-file shape: metadata rows, then the real header."""
        grid = [
            ["hospital_name", "last_updated_on", "version"],
            ["A Hospital", "7/1/2026", "3.0.0"],
            ["description", "code", "price"],
            ["X", "1", "10.00"],
        ]
        known = {"description", "code", "price"}
        score = lambda row: sum(1 for c in row if c.strip().casefold() in known)
        index, _ = find_header(grid, score)
        self.assertEqual(index, 2)

    def test_without_a_scorer_the_last_candidate_still_wins(self):
        grid = [["A", "B"], ["C", "D"], ["1", "2"]]
        self.assertEqual(find_header(grid)[0], 1)

    def test_when_nothing_looks_like_a_header_it_says_so(self):
        index, why = find_header([["1", "2"], ["3", "4"]])
        self.assertEqual(index, 0)
        self.assertIn("no row", why)


class ReadingCsv(unittest.TestCase):
    def test_a_plain_csv(self):
        path = temp("p.csv", "SKU,Price\nA,10.00\nB,9.00\n")
        table = read(path)[0]
        self.assertEqual(table.header, ["SKU", "Price"])
        self.assertEqual(len(table.rows), 2)

    def test_a_semicolon_file(self):
        path = temp("p.csv", "SKU;Price\nA;10,00\nB;9,00\n")
        table = read(path)[0]
        self.assertEqual(table.header, ["SKU", "Price"])

    def test_a_byte_order_mark_is_not_part_of_the_first_heading(self):
        path = Path(tempfile.mkdtemp()) / "p.csv"
        path.write_bytes("﻿SKU,Price\nA,10.00\n".encode("utf-8"))
        self.assertEqual(read(path)[0].header[0], "SKU")

    def test_wholly_blank_rows_are_dropped(self):
        path = temp("p.csv", "SKU,Price\nA,10.00\n,\nB,9.00\n")
        self.assertEqual(len(read(path)[0].rows), 2)

    def test_a_csv_cell_carries_no_format(self):
        path = temp("p.csv", "SKU,Price\nA,10.00\n")
        self.assertIsNone(read(path)[0].rows[0][1].format_decimals)

    def test_a_cell_larger_than_the_csv_default_limit_is_read(self):
        """`csv` raises above 128 kB, and hospital footnotes are paragraphs.

        Three of the 200 files in the reference corpus died on this — the
        crash was inside `csv.reader`, so the tool reported neither a finding
        nor a readable error, and the measurement counted them as crashes.
        """
        import csv as csv_module

        before = csv_module.field_size_limit()
        big = "x" * 200_000
        path = temp("p.csv", f'SKU,Notes,Price\nA,"{big}",10.00\nB,"{big}",9.00\n')
        table = read(path)[0]
        self.assertEqual(len(table.rows), 2)
        self.assertEqual(len(table.rows[0][1].text), 200_000)
        # The limit is process-wide, and a library must not leave it changed.
        self.assertEqual(csv_module.field_size_limit(), before)

    def test_an_unreadable_suffix_says_what_it_reads(self):
        path = temp("p.pdf", "not really a pdf")
        with self.assertRaises(UnreadableFile) as caught:
            read(path)
        self.assertIn(".csv", str(caught.exception))
        self.assertIn(".xlsx", str(caught.exception))

    def test_header_row_beyond_the_file_is_refused(self):
        path = temp("p.csv", "SKU,Price\nA,10.00\n")
        with self.assertRaises(UnreadableFile):
            read(path, header_row=99)


class NumberFormats(unittest.TestCase):
    """An .xlsx stores 12.34 as a number and its appearance somewhere else."""

    def test_a_format_with_no_fraction_shows_no_decimals(self):
        self.assertEqual(_format_decimals("#,##0"), 0)
        self.assertEqual(_format_decimals("General"), 0)

    def test_placeholders_after_the_point_are_counted(self):
        self.assertEqual(_format_decimals("#,##0.00"), 2)
        self.assertEqual(_format_decimals("0.0000"), 4)

    def test_a_currency_literal_says_nothing_about_precision(self):
        self.assertEqual(_format_decimals('"£"#,##0.00'), 2)

    def test_only_the_positive_section_is_read(self):
        self.assertEqual(_format_decimals("#,##0.00;[Red]-#,##0.0000"), 2)


def write_two_sheets(path: Path, sheets: dict[str, list[list[object]]]) -> None:
    """A workbook with more than one worksheet.

    `make_examples.write_xlsx` writes one, which left the loop over worksheets
    — and `--sheet` — with no test at all.
    """
    import make_examples as m

    overrides = []
    rels = []
    types = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
    ]
    entries = {}
    names = []
    for number, (name, rows) in enumerate(sheets.items(), start=1):
        target = f"xl/worksheets/sheet{number}.xml"
        body = []
        for row_index, row in enumerate(rows, start=1):
            cells = []
            for column_index, value in enumerate(row):
                reference = f"{m.column_letter(column_index)}{row_index}"
                if isinstance(value, (int, float)):
                    cells.append(f'<c r="{reference}"><v>{value}</v></c>')
                elif value:
                    cells.append(
                        f'<c r="{reference}" t="inlineStr"><is><t>{value}</t></is></c>'
                    )
            body.append(f'<row r="{row_index}">{"".join(cells)}</row>')
        entries[target] = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData>{"".join(body)}</sheetData></worksheet>'
        )
        types.append(
            f'<Override PartName="/{target}" ContentType="application/vnd.'
            'openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
        rels.append(
            f'<Relationship Id="rId{number}" Type="http://schemas.openxmlformats.org/'
            f'officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{number}.xml"/>'
        )
        names.append(f'<sheet name="{name}" sheetId="{number}" r:id="rId{number}"/>')
    types.append("</Types>")
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets>{"".join(names)}</sheets></workbook>'
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "".join(types))
        archive.writestr("_rels/.rels", m.ROOT_RELS)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
            f'relationships">{"".join(rels)}</Relationships>',
        )
        for target, content in entries.items():
            archive.writestr(target, content)


class ReadingXlsx(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp())

    def test_every_worksheet_is_read(self):
        """A price list routinely puts each product family on its own tab."""
        path = self.directory / "two.xlsx"
        write_two_sheets(path, {
            "Trade": [["SKU", "Price"], ["A", 10.0]],
            "Retail": [["SKU", "Price"], ["A", 20.0]],
        })
        tables = read(path)
        self.assertEqual([t.name for t in tables], ["Trade", "Retail"])
        self.assertEqual(tables[1].rows[0][1].text, "20.0")

    def test_sheet_selects_one(self):
        path = self.directory / "two.xlsx"
        write_two_sheets(path, {
            "Trade": [["SKU", "Price"], ["A", 10.0]],
            "Retail": [["SKU", "Price"], ["A", 20.0]],
        })
        tables = read(path, sheet="Retail")
        self.assertEqual([t.name for t in tables], ["Retail"])

    def test_a_sheet_name_that_is_not_there_is_refused(self):
        path = self.directory / "two.xlsx"
        write_two_sheets(path, {"Trade": [["SKU", "Price"], ["A", 10.0]]})
        with self.assertRaises(UnreadableFile):
            read(path, sheet="Nope")

    def test_values_and_declared_precision_both_come_through(self):
        path = self.directory / "book.xlsx"
        write_xlsx(path, "Sheet1", [
            ["SKU", "Price"],
            ["A", (10.0, 1)],
        ])
        table = read(path)[0]
        self.assertEqual(table.header, ["SKU", "Price"])
        self.assertEqual(table.rows[0][1].text, "10.0")
        self.assertEqual(table.rows[0][1].format_decimals, 2)

    def test_a_general_formatted_number_declares_nothing(self):
        path = self.directory / "book.xlsx"
        write_xlsx(path, "Sheet1", [["SKU", "Price"], ["A", 10.0]])
        self.assertIsNone(read(path)[0].rows[0][1].format_decimals)

    def test_a_gap_in_a_row_keeps_the_columns_lined_up(self):
        path = self.directory / "book.xlsx"
        write_xlsx(path, "Sheet1", [["A", "B", "C"], ["x", "", "z"]])
        row = read(path)[0].rows[0]
        self.assertEqual(row[0].text, "x")
        self.assertEqual(row[2].text, "z")

    def test_a_file_that_is_not_a_zip_is_refused_by_name(self):
        path = self.directory / "not.xlsx"
        path.write_text("plain text", encoding="utf-8")
        with self.assertRaises(UnreadableFile) as caught:
            read(path)
        self.assertIn("not a readable .xlsx", str(caught.exception))

    def test_an_entity_declaration_is_refused_before_it_is_expanded(self):
        """The billion-laughs attack, which `xml.etree` will happily perform.

        A spreadsheet is a file somebody sends you. Nine nested entities in a
        4 kB part expand to a gigabyte of string, and no part of a real .xlsx
        declares a document type, so the declaration itself is the signal.
        """
        bomb = (
            '<?xml version="1.0"?><!DOCTYPE lolz ['
            '<!ENTITY lol "lol">'
            + "".join(
                f'<!ENTITY lol{n} "{"&lol%d;" % (n - 1) * 10}">' if n > 1
                else '<!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">'
                for n in range(1, 10)
            )
            + "]><workbook>&lol9;</workbook>"
        )
        path = self.directory / "bomb.xlsx"
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", "<Types/>")
            archive.writestr("xl/workbook.xml", bomb)
            archive.writestr("xl/_rels/workbook.xml.rels", "<Relationships/>")
        with self.assertRaises(UnreadableFile) as caught:
            read(path)
        self.assertIn("document type", str(caught.exception))

    def test_a_part_claiming_to_be_enormous_is_refused_before_it_is_read(self):
        """A zip's headers are self-declared and this reads files people were sent."""
        path = self.directory / "bomb2.xlsx"
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", "<Types/>")
            archive.writestr("xl/workbook.xml", "<workbook/>")
        # Rewrite the declared uncompressed size without touching the payload.
        with zipfile.ZipFile(path) as archive:
            info = archive.getinfo("xl/workbook.xml")
        original = tables_module.LARGEST_PART
        try:
            tables_module.LARGEST_PART = 1
            with self.assertRaises(UnreadableFile) as caught:
                read(path)
            self.assertIn("will not read", str(caught.exception))
        finally:
            tables_module.LARGEST_PART = original
        self.assertGreater(info.file_size, 0)

    def test_a_corrupt_part_is_refused_rather_than_raising(self):
        """A zip checks its CRC when the part is unpacked, not when it opens.

        A truncated upload used to escape as a `zipfile.BadZipFile` traceback
        and exit 1 — the code that means findings were reported.
        """
        path = self.directory / "badcrc.xlsx"
        write_xlsx(path, "Sheet1", [["SKU", "Price"], ["A", 10.0]])
        raw = bytearray(path.read_bytes())
        # Corrupt the compressed bytes of the worksheet without touching the
        # headers, so the failure happens at decompression time.
        marker = raw.find(b"sheet1.xml")
        raw[marker + 40: marker + 60] = b"\x00" * 20
        path.write_bytes(bytes(raw))
        with self.assertRaises(UnreadableFile):
            read(path)

    def test_an_empty_workbook_is_refused(self):
        path = self.directory / "empty.xlsx"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("[Content_Types].xml", "<Types/>")
        with self.assertRaises(UnreadableFile):
            read(path)


class ARowOfTheWrongWidth(unittest.TestCase):
    """Rows whose cell count is not the header's are not read.

    Every case here reproduces the *shape* of a real published file, named in
    each test. No row of anyone's chargemaster is copied into this repository.
    """

    #: The shape of the header in
    #: `0042-380050-930508781 Sky Lakes Medical Center Standard Charges 2025.csv`
    #: — 29 columns, with a free-text description near the left and the
    #: de-identified minimum and maximum ten columns to the right of it. An
    #: unquoted comma in the description shifts both of them.
    SKY_LAKES_SHAPE = (
        "billing_class,description,code|1,standard_charge|gross,"
        "De-Identified IP Max,De-Identified IP Min\n"
    )

    def test_a_row_with_more_cells_than_the_header_is_not_read(self):
        path = temp("wide.csv", self.SKY_LAKES_SHAPE
                    + "IP,A widget,100,50.00,80,20\n"
                    + "IP,A widget, with a comma,200,50.00,80,20\n")
        table = read(path)[0]
        self.assertEqual(len(table.rows), 1)
        self.assertEqual(table.wider_than_header, 1)
        self.assertEqual(table.narrower_than_header, 0)

    def test_a_row_that_does_not_reach_the_headings_is_not_read(self):
        path = temp("narrow.csv", self.SKY_LAKES_SHAPE
                    + "IP,A widget,100,50.00,80,20\n"
                    + "IP,A widget,100\n")
        table = read(path)[0]
        self.assertEqual(len(table.rows), 1)
        self.assertEqual(table.narrower_than_header, 1)

    def test_the_rows_that_are_read_still_cite_their_own_line(self):
        """A finding names a line in the file, so dropping a row cannot shift it."""
        path = temp("lines.csv", self.SKY_LAKES_SHAPE
                    + "IP,A widget, with a comma,200,50.00,80,20\n"
                    + "IP,A widget,100,50.00,80,20\n")
        table = read(path)[0]
        self.assertEqual(table.row_numbers, [3])

    def test_a_trailing_comma_on_the_header_does_not_condemn_every_row(self):
        """The shape of `0125-041316-800370789_MCHS-SMC-REGIONAL-MEDICAL-CENTER`.

        Its header line ends in a comma, so it parses to 25 headings of which
        the last is empty, above 1,444,617 data rows of 24 cells. A row must
        reach every heading that has a name; it need not reach one that has
        none, or the whole file is lost.
        """
        path = temp("trailing.csv", "description,code|1,standard_charge|gross,\n"
                                    "A widget,100,50.00\n"
                                    "Another,101,60.00\n")
        table = read(path)[0]
        self.assertEqual(len(table.rows), 2)
        self.assertEqual(table.set_aside_for_width, 0)

    def test_a_row_may_fill_a_column_the_header_did_not_name(self):
        """The shape of `0161-231330-381415390_deckerville-community-hospital`.

        Its header line ends in three commas and its 27,356 data rows put a
        value in the last of the columns those commas open. Dropping the
        unnamed headings and then calling those rows too wide emptied the
        file — measured, on the first run of this rule.
        """
        path = temp("unnamed.csv", "description,code|1,standard_charge|gross,,\n"
                                   "A widget,100,50.00,,360\n")
        table = read(path)[0]
        self.assertEqual(len(table.rows), 1)
        self.assertEqual(table.set_aside_for_width, 0)

    def test_a_cell_past_the_header_line_is_not_excused_by_being_blank(self):
        """An unquoted comma pushes the last field off the end, blank or not.

        Reading a row because its tail looks empty leaves the shift in the
        middle of it in place. On the first run of this rule that let 158,000
        of one file's shifted rows through, and the check they corrupted lost
        only two thirds of its wrong findings instead of all of them.
        """
        path = temp("blanktail.csv", "description,code|1,standard_charge|gross\n"
                                     "A widget,100,50.00,\n")
        table = read(path)[0]
        self.assertEqual(len(table.rows), 0)
        self.assertEqual(table.wider_than_header, 1)

    def test_a_short_row_in_a_workbook_is_read(self):
        """An .xlsx states each cell's column, so a short row is not shifted.

        The rule is about delimited text, where position is counted from the
        commas. A worksheet that simply stops writing cells at the last filled
        one must not lose them.
        """
        path = self.directory / "short.xlsx"
        write_xlsx(path, "Sheet1", [["SKU", "Quantity", "Unit price"],
                                    ["A", 1, 10.0],
                                    ["B"]])
        table = read(path)[0]
        self.assertEqual(len(table.rows), 2)
        self.assertEqual(table.set_aside_for_width, 0)

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp())


class AJsonDocumentNamedCsv(unittest.TestCase):
    """27 of the 200 files in the hospital corpus are this.

    They are the CMS schema's JSON form served from a URL ending `.csv`, and
    one of them reads as a single row of up to 1.16 million comma-separated
    fields. No check could ever find a column in that, so the run already
    ended in exit 2 and invented nothing — but it never said the file is not
    a table, and a reader had to work it out from the column count.
    """

    def test_it_is_refused_and_says_it_is_not_a_table(self):
        path = temp("standardcharges.csv",
                    '{"hospital_name": "A Hospital", "standard_charge_information": []}')
        with self.assertRaises(UnreadableFile) as caught:
            read(path)
        self.assertIn("JSON", str(caught.exception))
        self.assertIn("not a table", str(caught.exception))

    def test_a_price_list_whose_first_cell_starts_with_a_bracket_is_still_read(self):
        path = temp("brackets.csv", "[group],Price\n[A],10.00\n")
        self.assertEqual(len(read(path)[0].rows), 1)


if __name__ == "__main__":
    unittest.main()
