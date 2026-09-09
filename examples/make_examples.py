#!/usr/bin/env python3
"""Builds the example files, including the .xlsx, with nothing but the stdlib.

An .xlsx is a zip of XML. Writing one by hand here keeps the repository's
promise of no dependencies honest all the way to its own examples, and it is
also the only way to plant a cell whose *stored* value and *displayed*
precision differ — which is the thing the XLSX reader exists to get right.

    python3 examples/make_examples.py
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>"""

ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

WORKBOOK_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

# Two cell formats: index 0 is General, index 1 shows two decimals.
STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="1"><numFmt numFmtId="164" formatCode="#,##0.00"/></numFmts>
<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>
<fills count="1"><fill><patternFill patternType="none"/></fill></fills>
<borders count="1"><border/></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="2">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
</cellXfs>
</styleSheet>"""


def column_letter(index: int) -> str:
    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def write_xlsx(path: Path, sheet_name: str, rows: list[list[object]]) -> None:
    """Write a workbook. A tuple ``(value, style)`` picks a cell format."""
    body = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for column_index, value in enumerate(row):
            reference = f"{column_letter(column_index)}{row_index}"
            style = 0
            if isinstance(value, tuple):
                value, style = value
            attribute = f' s="{style}"' if style else ""
            if isinstance(value, (int, float)):
                cells.append(f'<c r="{reference}"{attribute}><v>{value}</v></c>')
            elif value is None or value == "":
                continue
            else:
                cells.append(
                    f'<c r="{reference}"{attribute} t="inlineStr">'
                    f"<is><t>{escape(str(value))}</t></is></c>"
                )
        body.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(body)}</sheetData></worksheet>'
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets><sheet name="{escape(sheet_name)}" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", ROOT_RELS)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", WORKBOOK_RELS)
        archive.writestr("xl/styles.xml", STYLES)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)


def main() -> None:
    write_xlsx(
        HERE / "rate-card.xlsx",
        "Rate card",
        [
            ["Acme Components — trade rate card"],
            ["Prices in GBP, excluding VAT"],
            [],
            ["Part number", "Quantity", "List price", "Discount %", "Net price",
             "Min charge", "Max charge"],
            # Reconciles: 100 less 10% is 90.
            ["AC-1", 1, (100.0, 1), 10, (90.0, 1), (25.0, 1), (250.0, 1)],
            # Does not: 100 less 15% is 85, not 88.
            ["AC-1", 25, (100.0, 1), 15, (88.0, 1), (25.0, 1), (250.0, 1)],
            # A bigger order given a smaller discount.
            ["AC-1", 100, (100.0, 1), 12, (88.0, 1), (25.0, 1), (250.0, 1)],
            # A minimum above its own maximum.
            ["AC-2", 1, (60.0, 1), 0, (60.0, 1), (400.0, 1), (300.0, 1)],
            # Stored to four places, displayed to two: 42.5049 shows as 42.50,
            # and a tolerance taken from the stored value would be wrong.
            ["AC-3", 1, (50.005, 1), 15, (42.50425, 1), (10.0, 1), (99.0, 1)],
        ],
    )
    print("wrote rate-card.xlsx")


if __name__ == "__main__":
    main()
