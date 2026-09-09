"""Working out what each column of a price list is, from what it is called.

A price list has no schema. The only thing every one of them shares is that a
human wrote a word at the top of each column, so that word is what this reads.

Two rules keep that from becoming a guessing machine.

**A role comes from the column's name, never from the shape of its contents.**
A column of numbers between 0 and 100 could be a discount percentage, a
quantity break, a case pack or a stock figure, and picking one because the
numbers look right is how a tool invents a contradiction. What the contents
are for is refusal: a column named like a price that holds no readable number
is reported as recognised-but-unusable, not quietly used.

**A name matching two roles equally matches neither.** The column is reported
as ambiguous, with both candidates named, and no check uses it. ``--map`` is
how a person settles it, and a settled column says so in the report.

The whole vocabulary is printed by ``adds-up --list-columns``. It is a
vocabulary and not a language: a header this tool has never seen gets no role,
the checks that needed it do not run, and the report says which word it was
looking for. That is the difference between a column it could not read and a
column with nothing wrong in it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: What a column can be. Every check names the roles it needs, and a check
#: whose roles are missing does not run.
ROLES = (
    "item",
    "quantity",
    "unit_price",
    "list_price",
    "net_price",
    "discount_percent",
    "percent_of_list",
    "adjustment",
    "currency",
    "unit",
    "minimum",
    "maximum",
    "components",
    "qualifier",
)

ROLE_MEANING = {
    "item": "what is being priced — a code, a SKU, a description",
    "quantity": "how many, or the top or bottom of a volume band",
    "unit_price": "the price of one unit",
    "list_price": "the price before any discount",
    "net_price": "the price after any discount",
    "discount_percent": "a discount stated as a percentage off the list price",
    "percent_of_list": "a price stated as a percentage OF the list price",
    "adjustment": "an adder applied to the price in the same row",
    "currency": "the currency a row's money is in",
    "unit": "the unit the price is per",
    "minimum": "the bottom of a stated range",
    "maximum": "the top of a stated range",
    "components": "the items a bundle is made of, named in this document",
    "qualifier": "something that legitimately makes two rows different prices",
}

#: Exact matches, after folding. First and strongest.
EXACT: dict[str, tuple[str, ...]] = {
    "item": (
        "item", "item code", "item no", "item number", "item id", "sku",
        "product", "product code", "product id", "product number", "part",
        "part no", "part number", "code", "catalogue number", "catalog number",
        "model", "model number", "article", "article number", "reference",
        "service", "service code", "description", "line item", "mpn",
    ),
    "quantity": (
        "quantity", "qty", "volume", "tier", "band", "break", "quantity break",
        "volume tier", "price break", "pack size", "case quantity", "units",
        "from", "to", "up to", "from quantity", "to quantity", "min quantity",
        "max quantity", "minimum quantity", "maximum quantity", "lot size",
        "order quantity", "threshold", "step", "annual volume",
    ),
    "unit_price": (
        "unit price", "price per unit", "price each", "each", "rate",
        "unit rate", "unit cost", "per unit", "price per", "unit charge",
        "rate per unit",
    ),
    "list_price": (
        "list price", "list", "gross price", "gross", "rrp", "msrp",
        "recommended retail price", "standard price", "standard charge",
        "catalogue price", "catalog price", "full price", "before discount",
        "undiscounted price", "book price",
    ),
    "net_price": (
        "net price", "net", "discounted price", "your price", "sale price",
        "final price", "after discount", "contract price", "negotiated price",
        "negotiated dollar", "discounted cash", "customer price", "offer price",
        "price", "amount", "charge", "cost", "value", "fee", "tariff",
    ),
    "discount_percent": (
        "discount", "discount percent", "discount percentage", "discount pct",
        "percent off", "off", "percentage discount",
        "rebate percent", "reduction", "discount rate",
    ),
    "percent_of_list": (
        "negotiated percentage", "percent of charge", "percentage of charge",
        "percent of list", "percentage of list", "percent of gross",
        "percentage of gross", "percent of billed charges",
    ),
    "adjustment": (
        "adjustment", "adj", "adder", "surcharge", "uplift", "rider",
        "adjustment per unit",
    ),
    "currency": ("currency", "currency code", "ccy", "cur", "iso currency"),
    "unit": (
        "unit", "uom", "unit of measure", "measure", "per", "units of measure",
        "unit type", "pricing unit", "unit of measurement",
        # `drug_type_of_measure(ment)` holds the unit — ML, GR, UN — and
        # `drug_unit_of_measure(ment)` holds the *amount*. The names read the
        # other way round, and reading them that way had this tool reporting
        # that a drug was "priced in 2 different units: 1357.2 and 8".
        "drug type of measurement", "drug type of measure",
    ),
    "minimum": (
        "min", "minimum", "min price", "minimum price", "lower", "lower bound",
        "min charge", "minimum charge", "min amount", "floor", "min rate",
    ),
    "maximum": (
        "max price", "maximum price", "maximum", "upper", "upper bound",
        "max charge", "maximum charge", "max amount", "ceiling", "max rate",
    ),
    "components": (
        "components", "component", "contains", "includes", "made up of",
        "bundle contents", "kit contents", "parts included", "consists of",
        "bill of materials", "bom",
    ),
}

#: Matched on the last word or two of a compound name, after the exact table
#: has failed. This is what reads ``standard_charge|Aetna|PPO|negotiated_dollar``
#: without needing to have heard of Aetna.
SUFFIX: tuple[tuple[str, str], ...] = (
    ("negotiated dollar", "net_price"),
    ("negotiated percentage", "percent_of_list"),
    ("percent of charge", "percent_of_list"),
    ("percentage of charge", "percent_of_list"),
    ("discounted cash", "net_price"),
    ("estimated amount", "net_price"),
    ("gross", "list_price"),
    ("min", "minimum"),
    ("max", "maximum"),
    ("unit price", "unit_price"),
    ("list price", "list_price"),
    ("net price", "net_price"),
    ("discount", "discount_percent"),
    ("currency", "currency"),
)

#: Names that make a row legitimately different from another row with the same
#: item. Two prices for the same SKU in two of these are two prices, not a
#: contradiction, so they are part of the identity a duplicate is judged on.
#:
#: Matched as the whole name, or as the first or last word of a compound one,
#: so ``payer_name`` and ``customer group`` are both caught without either
#: being written out. Plurals are listed rather than stemmed: guessing that a
#: trailing ``s`` is a plural turns ``status`` into ``statu``.
QUALIFIER: tuple[str, ...] = (
    # A free-text note attached to a row is, by definition, something about
    # that row the other columns do not say. Where two otherwise identical
    # rows carry different notes, the document is distinguishing them and this
    # tool should not overrule it. Ten of thirty audited `two-prices` findings
    # were two rows separated only by a note reading "Gross Charge Type: Sta"
    # against "Gross Charge Type: Fee".
    "notes", "note", "comment", "comments", "remark", "remarks",
    "additional generic notes", "additional payer notes", "footnote",
    # An amount, not a unit: two rows for the same drug covering different
    # amounts are two prices for two things, so it separates them.
    "drug unit of measurement", "drug unit of measure",
    "modifiers", "rider category", "fare media",
    "payment method", "transfers", "agency", "network", "methodology",
    "region", "country", "territory", "zone", "state", "market", "location",
    "customer", "customer group", "channel", "segment", "tier name", "plan",
    "payer", "contract", "agreement", "price list", "effective", "valid from",
    "valid to", "start date", "end date", "date", "year", "season", "version",
    "setting", "billing class", "modifier", "supplier", "vendor", "warehouse",
    "branch", "grade", "colour", "color", "size", "variant", "option",
    "condition", "period", "term", "duration", "frequency", "class",
)

#: Words that make a compound name an item identifier when they lead it.
ITEM_PREFIXES = ("code", "sku", "item", "part", "product", "article", "model")

_PUNCTUATION = re.compile(r"[|/\\_\-–—:;.,()\[\]{}#*]+")
_SPACES = re.compile(r"\s+")


def fold(name: str) -> str:
    """Reduce a header to the form the vocabulary is written in."""
    text = str(name).replace("%", " percent ")
    text = _PUNCTUATION.sub(" ", text)
    text = _SPACES.sub(" ", text).strip().casefold()
    text = re.sub(r"\bnos?\b", "no", text)
    text = re.sub(r"\bpct\b", "percent", text)
    text = re.sub(r"\bqty\b", "qty", text)
    if text.endswith("(s)"):
        text = text[:-3]
    return text.strip()


@dataclass(frozen=True)
class Column:
    """One column, and what this tool decided it is."""

    index: int
    name: str
    role: str | None
    reason: str
    family: str = ""
    candidates: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        return self.name or f"column {self.index + 1}"


def _family_of(folded: str, matched: str) -> str:
    """The part of a compound name in front of the word that gave the role.

    ``standard charge aetna ppo negotiated dollar`` has family ``aetna ppo``,
    which is how a percentage column is paired with the dollar column it is a
    percentage of, and not with some other payer's.
    """
    if folded.endswith(matched):
        head = folded[: -len(matched)].strip()
    else:
        head = folded
    for prefix in ("standard charge", "price", "rate", "charge"):
        if head.startswith(prefix):
            head = head[len(prefix):].strip()
    return head


def classify(header: list[str], overrides: dict[int, str] | None = None) -> list[Column]:
    """Give every column a role, or none, with a printable reason for each."""
    overrides = overrides or {}
    out: list[Column] = []
    for index, name in enumerate(header):
        if index in overrides:
            role = overrides[index]
            out.append(
                Column(index, name, role, f"set to {role} by --map", family="")
            )
            continue
        folded = fold(name)
        if not folded:
            out.append(Column(index, name, None, "the column has no heading"))
            continue

        hits = [role for role, names in EXACT.items() if folded in names]
        if len(hits) == 1:
            out.append(
                Column(index, name, hits[0], f"'{folded}' is a known name for {hits[0]}")
            )
            continue
        if len(hits) > 1:
            out.append(
                Column(
                    index, name, None,
                    f"'{folded}' is a known name for {' and '.join(sorted(hits))}, "
                    "so it was not used; --map settles it",
                    candidates=tuple(sorted(hits)),
                )
            )
            continue

        if folded in QUALIFIER or any(
            folded.endswith(" " + word) or folded.startswith(word + " ")
            for word in QUALIFIER
        ):
            out.append(
                Column(index, name, "qualifier", f"'{folded}' names something that "
                       "makes two rows legitimately different")
            )
            continue

        # A published schema numbers its identifier columns: `code|1`,
        # `code|2`, `code|1|type`. All of them name what is being priced.
        if any(folded.startswith(word + " ") for word in ITEM_PREFIXES):
            out.append(
                Column(index, name, "item",
                       f"'{folded}' begins with '{folded.split()[0]}', a known name for item")
            )
            continue

        matched = [(text, role) for text, role in SUFFIX if folded.endswith(text)]
        if matched:
            text, role = max(matched, key=lambda pair: len(pair[0]))
            out.append(
                Column(
                    index, name, role,
                    f"'{folded}' ends in '{text}', a known name for {role}",
                    family=_family_of(folded, text),
                )
            )
            continue

        out.append(
            Column(index, name, None, f"'{folded}' is not a name this tool knows")
        )
    return reconcile(out, set(overrides))


#: Bare names that mean the top or bottom of a band of quantity in one table
#: and the ends of a price range in another. Nothing inside the word settles
#: it; what settles it is whether the other end of a range is present.
#: ``from``/``to``/``up to`` are deliberately absent: those name a band of
#: quantity in every price list seen while building this, and reading them as
#: the ends of a price range would be wrong every time.
BARE_BOUNDS = {"max": "maximum", "maximum": "maximum",
               "min": "minimum", "minimum": "minimum"}


def reconcile(columns: list[Column], settled: set[int]) -> list[Column]:
    """Settle the two names that only the rest of the table can settle.

    A column called ``max`` is the top of a volume band in a tier table and
    the top of a price range in a rate sheet, and the word is the same in
    both. The rule is that a bound is a *range* end only when the other end
    is there too, and a *quantity* otherwise. Both readings are common and
    real, and choosing on the word alone gets one of them wrong every time.
    """
    bare: dict[str, list[int]] = {"minimum": [], "maximum": []}
    for position, column in enumerate(columns):
        if column.index in settled:
            continue
        folded = fold(column.name)
        if folded in BARE_BOUNDS and not _family_of(folded, folded):
            bare[BARE_BOUNDS[folded]].append(position)
    if not bare["minimum"] or not bare["maximum"]:
        # Only one end is present, so nothing here is a range.
        for end, positions in bare.items():
            for position in positions:
                column = columns[position]
                columns[position] = Column(
                    column.index, column.name, "quantity",
                    f"'{fold(column.name)}' is the edge of a band; no column names "
                    f"the other end of a range, so it was not read as one",
                )
        return columns
    for end, positions in bare.items():
        for position in positions:
            column = columns[position]
            columns[position] = Column(
                column.index, column.name, end,
                f"'{fold(column.name)}' is read as the {end} of a range because a "
                f"column naming the other end is present",
            )
    return columns


def vocabulary_lines() -> list[str]:
    """Everything the tool will recognise, for ``--list-columns``."""
    lines = []
    for role in ROLES:
        if role == "qualifier":
            continue
        lines.append(f"{role} — {ROLE_MEANING[role]}")
        for name in sorted(EXACT.get(role, ())):
            lines.append(f"    {name}")
        endings = sorted(text for text, mapped in SUFFIX if mapped == role)
        for text in endings:
            lines.append(f"    ...ending in '{text}'")
        lines.append("")
    lines.append(f"qualifier — {ROLE_MEANING['qualifier']}")
    for name in sorted(QUALIFIER):
        lines.append(f"    {name}")
    return lines
