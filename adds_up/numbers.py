"""Turning printed cells into numbers, and refusing when the printing is ambiguous.

The whole tool is arithmetic on values a document prints, so the reading of a
printed value is the load-bearing part. Two things here are not obvious and
both were arrived at by being wrong first.

**A separator is decided per column, not per cell.** ``1,234`` is 1234 in a
document written for the United States and 1.234 in one written for Germany,
and no amount of staring at that one cell settles it. So the decision is made
once for a whole column, from the cells in it that are unambiguous, and a
column with no unambiguous cell is refused rather than guessed. A guess here
does not produce a wrong number in one row; it produces a finding about a
contradiction that does not exist.

**Precision is kept.** ``10.00`` and ``10`` are the same number and not the
same printed value. A discount that reconciles to the precision the document
itself prints is reconciled, and the tolerance for that comes from the cell,
not from a constant somebody picked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

#: Currency symbols and codes recognised where they sit against a number.
#: This is a vocabulary, not a detector: a symbol not in here is not a
#: currency as far as this tool is concerned, and the report says so rather
#: than treating the cell as plain.
CURRENCY_SYMBOLS = {
    "$": "USD", "US$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY",
    "₹": "INR", "Rs": "INR", "₩": "KRW", "R$": "BRL", "CHF": "CHF",
    "kr": "SEK", "zł": "PLN", "₽": "RUB", "A$": "AUD", "C$": "CAD",
    "NZ$": "NZD", "HK$": "HKD", "S$": "SGD", "₺": "TRY", "R": "ZAR",
}

#: Three-letter codes accepted when they appear beside a number or alone in a
#: currency column. Deliberately not "any three uppercase letters": ``NET`` and
#: ``EUR`` are the same shape.
CURRENCY_CODES = {
    "USD", "EUR", "GBP", "JPY", "INR", "AUD", "CAD", "NZD", "CHF", "SEK",
    "NOK", "DKK", "PLN", "CZK", "HUF", "RON", "BGN", "HRK", "TRY", "RUB",
    "ZAR", "BRL", "MXN", "ARS", "CLP", "COP", "PEN", "CNY", "HKD", "SGD",
    "KRW", "TWD", "THB", "MYR", "IDR", "PHP", "VND", "AED", "SAR", "ILS",
    "EGP", "NGN", "KES", "PKR", "BDT", "LKR", "NPR", "ISK", "UAH", "RSD",
}

_TRAILING_MINUS = re.compile(r"^(.*?)-\s*$")
_PARENTHESISED = re.compile(r"^\((.*)\)$")
_NUMERIC_BODY = re.compile(r"^[0-9][0-9.,   ]*[0-9]$|^[0-9]$")

#: A value that means "nothing printed here", not "zero".
BLANKS = {"", "-", "–", "—", "n/a", "na", "nil", "none", "tbd", "tba",
          "not applicable", "not available", ".", "..", "...", "#n/a", "null"}


@dataclass(frozen=True)
class Printed:
    """A number as the document printed it.

    ``value`` is what it means. ``decimals`` is how many digits followed the
    decimal separator as printed, which is what sets the tolerance when this
    number is compared with one derived from others. ``percent`` records that
    the cell carried a ``%`` sign, because 15 and 15% are not the same claim.
    """

    value: Decimal
    decimals: int
    text: str
    currency: str | None = None
    percent: bool = False

    def tolerance(self) -> Decimal:
        """Half of the last printed digit.

        A price printed as ``12.34`` stands for anything in ``[12.335,
        12.345)``. Comparing a derived figure against it any more tightly than
        that reports a contradiction that is only rounding.
        """
        return Decimal(1).scaleb(-self.decimals) / 2


@dataclass(frozen=True)
class Convention:
    """Which character groups digits and which one splits the fraction."""

    decimal: str
    group: str

    @property
    def name(self) -> str:
        return "1,234.56" if self.decimal == "." else "1.234,56"


DOT_DECIMAL = Convention(decimal=".", group=",")
COMMA_DECIMAL = Convention(decimal=",", group=".")


def strip_currency(text: str) -> tuple[str, str | None]:
    """Pull a leading or trailing currency marker off a cell.

    Returns the rest of the cell and the ISO code, or ``None`` when there is
    no marker this tool recognises.
    """
    cleaned = text.strip()
    for symbol in sorted(CURRENCY_SYMBOLS, key=len, reverse=True):
        if cleaned.startswith(symbol) and cleaned[len(symbol):].strip():
            return cleaned[len(symbol):].strip(), CURRENCY_SYMBOLS[symbol]
    for symbol in sorted(CURRENCY_SYMBOLS, key=len, reverse=True):
        if cleaned.endswith(symbol) and cleaned[: -len(symbol)].strip():
            return cleaned[: -len(symbol)].strip(), CURRENCY_SYMBOLS[symbol]
    head, _, tail = cleaned.partition(" ")
    if head.upper() in CURRENCY_CODES:
        return tail.strip(), head.upper()
    if tail.strip().upper() in CURRENCY_CODES:
        return head.strip(), tail.strip().upper()
    return cleaned, None


def _shape(body: str) -> str:
    """Classify what the separators in a numeric body can mean.

    ``unambiguous-dot``   the ``.`` must be a decimal point
    ``unambiguous-comma`` the ``,`` must be a decimal comma
    ``ambiguous``         one separator, three digits after it: could be either
    ``plain``             no separator at all
    """
    body = body.replace(" ", "").replace(" ", "").replace(" ", "")
    dots = body.count(".")
    commas = body.count(",")
    if dots and commas:
        return "unambiguous-dot" if body.rindex(".") > body.rindex(",") else "unambiguous-comma"
    if dots == 0 and commas == 0:
        return "plain"
    separator = "." if dots else ","
    count = dots or commas
    head, tail = body.rsplit(separator, 1)
    if count > 1:
        # 1.234.567 can only be grouping.
        return "unambiguous-comma" if separator == "." else "unambiguous-dot"
    decimal_here = "unambiguous-dot" if separator == "." else "unambiguous-comma"
    if len(tail) != 3:
        # 1.5 or 1,5 or 12.3456 — a group is always exactly three digits.
        return decimal_here
    # Three digits after a single separator is the ambiguous case — but only
    # when what precedes it could be a group. A group is one to three digits
    # and never carries a leading zero, so 0.091 and 1234.567 are decimals in
    # both conventions and only 1.234 is genuinely undecidable. Calling those
    # ambiguous refused 1,898 real tariffs whose rates all look like 0.091.
    if not head or head.startswith("0") or len(head) > 3:
        return decimal_here
    return "ambiguous"


def convention_of(cells: list[str]) -> tuple[Convention | None, str]:
    """Decide the separator convention for a whole column.

    Returns the convention and a plain sentence explaining the decision, which
    the report prints when a column is refused. A column whose every numeric
    cell is ``ambiguous`` gets ``None``: ``1,234`` on its own is 1234 or 1.234
    and this tool will not pick one.
    """
    dot = comma = ambiguous = plain = 0
    for cell in cells:
        body, _ = strip_currency(str(cell).strip().rstrip("%").strip())
        body = body.strip()
        match = _PARENTHESISED.match(body)
        if match:
            body = match.group(1).strip()
        body = body.lstrip("+-").strip()
        if not body or body.lower() in BLANKS:
            continue
        if not _NUMERIC_BODY.match(body):
            continue
        shape = _shape(body)
        if shape == "unambiguous-dot":
            dot += 1
        elif shape == "unambiguous-comma":
            comma += 1
        elif shape == "ambiguous":
            ambiguous += 1
        else:
            plain += 1
    if dot and comma:
        return None, (
            f"the column mixes both conventions: {dot} cell(s) can only be read as "
            f"1,234.56 and {comma} cell(s) can only be read as 1.234,56"
        )
    if dot:
        return DOT_DECIMAL, f"{dot} cell(s) in this column can only be read as 1,234.56"
    if comma:
        return COMMA_DECIMAL, f"{comma} cell(s) in this column can only be read as 1.234,56"
    if ambiguous:
        return None, (
            f"{ambiguous} cell(s) carry a single separator followed by exactly three "
            "digits, which is 1,234 in one convention and 1.234 in the other, and no "
            "other cell in the column settles which"
        )
    if plain:
        return DOT_DECIMAL, "no cell in this column carries a separator"
    return None, "the column holds no number"


def parse(text: str, convention: Convention) -> Printed | None:
    """Read one printed cell under a decided convention.

    ``None`` means the cell holds no number — including when it holds one of
    the many things people type to mean "nothing here". A blank is not a zero
    and is never treated as one.
    """
    raw = str(text).strip()
    if not raw or raw.strip().lower() in BLANKS:
        return None

    body, currency = strip_currency(raw)
    percent = body.endswith("%")
    if percent:
        body = body[:-1].strip()
        body, extra = strip_currency(body)
        currency = currency or extra

    negative = False
    match = _PARENTHESISED.match(body)
    if match:
        negative = True
        body = match.group(1).strip()
        body, extra = strip_currency(body)
        currency = currency or extra
    match = _TRAILING_MINUS.match(body)
    if match and match.group(1).strip():
        negative = True
        body = match.group(1).strip()
    if body.startswith("-"):
        negative = True
        body = body[1:].strip()
    elif body.startswith("+"):
        body = body[1:].strip()

    body = body.replace(" ", "").replace(" ", "").replace(" ", "")
    if not body or not _NUMERIC_BODY.match(body):
        return None

    body = body.replace(convention.group, "")
    if body.count(convention.decimal) > 1:
        return None
    decimals = 0
    if convention.decimal in body:
        decimals = len(body.rsplit(convention.decimal, 1)[1])
        body = body.replace(convention.decimal, ".")
    try:
        value = Decimal(body)
    except InvalidOperation:
        return None
    if negative:
        value = -value
    return Printed(
        value=value, decimals=decimals, text=raw, currency=currency, percent=percent
    )


def is_blank(text: str) -> bool:
    """Whether a cell says nothing, as opposed to saying zero."""
    return str(text).strip().lower() in BLANKS
