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


class ReadingXlsx(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp())

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

    def test_an_empty_workbook_is_refused(self):
        path = self.directory / "empty.xlsx"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("[Content_Types].xml", "<Types/>")
        with self.assertRaises(UnreadableFile):
            read(path)


if __name__ == "__main__":
    unittest.main()
