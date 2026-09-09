"""The seven checks. All of them are arithmetic on values the document prints.

Every one obeys the same three rules.

**Both halves of the comparison come from the input.** Nothing here reaches
for a cost, a margin, a benchmark or a market price. A price list does not
state a cost, so this tool can say nothing whatever about margin, and does
not.

**A missing column is a check that did not run, not a check that passed.**
Each check declares the roles it needs. When one is absent the check records
why, and the report prints that beside the checks that did run.

**A finding states what two rows say.** It never says the pricing is wrong.
"Row 12 prices 500 units at 4.10 each and row 11 prices 100 units at 3.90
each" is a finding. "Your tier pricing is broken" is not, and no phrasing in
this module comes close to it.
"""

from __future__ import annotations

from decimal import Decimal

from .columns import Column, fold
from .models import CheckRun, Finding, Place
from .numbers import Convention, Printed, is_blank, parse

CHECK_NAMES = (
    "volume-tier",
    "discount-tier",
    "bundle-above-parts",
    "stated-discount",
    "two-prices",
    "inverted-range",
    "unit-mismatch",
)

CHECK_DESCRIPTIONS = {
    "volume-tier": "a larger quantity priced higher than a smaller one, in the price column named",
    "discount-tier": "a larger quantity given a smaller discount than a smaller one",
    "bundle-above-parts": "a bundle priced above the sum of the parts this document says it contains",
    "stated-discount": "a discount percentage that does not reconcile with the two prices beside it",
    "two-prices": "the same item priced twice, differently, with nothing to tell the rows apart",
    "inverted-range": "a stated minimum above its own stated maximum",
    "unit-mismatch": "one item priced in two different units or two different currencies",
}


class Reader:
    """A table's cells, read under the conventions decided for each column."""

    def __init__(self, sheet, header, rows, columns, conventions, header_row_number,
                 reasons=None):
        self.sheet = sheet
        self.header = header
        self.rows = rows
        self.columns = columns
        self.conventions = conventions
        self.header_row_number = header_row_number
        #: Why each numeric column was read the way it was, or refused. Quoted
        #: verbatim when a check cannot run, because "could not be read" and
        #: "holds no number at all" are different facts about a document.
        self.reasons = reasons or {}

    def unreadable(self, column: Column) -> str:
        return (
            f"'{column.label}' holds no number this tool could use: "
            + self.reasons.get(column.index, "no reason was recorded")
        )

    def by_role(self, role: str) -> list[Column]:
        return [c for c in self.columns if c.role == role]

    def first(self, *roles: str) -> Column | None:
        """The leftmost column in the first of these roles that is present."""
        for role in roles:
            found = self.by_role(role)
            if found:
                return found[0]
        return None

    def first_usable(self, *roles: str) -> Column | None:
        """The leftmost column whose numbers can actually be read.

        A published file routinely carries several columns in one role with
        only some of them filled in: a hospital's standard-charges file has a
        cash price and a negotiated price side by side, and a hospital that
        negotiates but publishes no cash price leaves the first of them empty
        throughout. Taking the leftmost regardless meant the check reported
        that it could not run while a perfectly readable column sat next to
        the one it had chosen.

        Falls back to ``first`` so that the reason reported names a real
        column rather than nothing.
        """
        for role in roles:
            found = self.by_role(role)
            for column in found:
                if self.conventions.get(column.index) is not None:
                    return column
        return self.first(*roles)

    def text(self, row_index: int, column: Column) -> str:
        row = self.rows[row_index]
        if column.index >= len(row):
            return ""
        return row[column.index].text

    def number(self, row_index: int, column: Column) -> Printed | None:
        convention = self.conventions.get(column.index)
        if convention is None:
            return None
        raw = self.text(row_index, column)
        printed = parse(raw, convention)
        if printed is None:
            return None
        row = self.rows[row_index]
        if column.index < len(row):
            declared = row[column.index].format_decimals
            if declared is not None and declared > printed.decimals:
                printed = Printed(
                    printed.value, declared, printed.text,
                    printed.currency, printed.percent,
                )
        return printed

    def place(self, row_index: int, column: Column) -> Place:
        return Place(self.sheet, self.header_row_number + 1 + row_index, column.label)

    def line(self, row_index: int) -> int:
        return self.header_row_number + 1 + row_index


def _group_key(reader: Reader, row_index: int, item: Column, qualifiers: list[Column]):
    return (
        reader.text(row_index, item).strip().casefold(),
        tuple(reader.text(row_index, q).strip().casefold() for q in qualifiers),
    )


def _groups(reader: Reader, item: Column | None, qualifiers: list[Column]):
    """Rows gathered by the thing they price, keyed by folded value.

    The value is folded so that ``W-100`` and ``w-100`` are one item, and the
    printed form of the first row in each group is kept alongside, because a
    finding must quote the document rather than this tool's normalisation.

    With no item column the whole table is one group, which is right for a
    single product's tier table and is the shape most tier tables come in.
    """
    if item is None:
        return {("", ()): (list(range(len(reader.rows))), "")}
    out: dict[tuple, tuple[list[int], str]] = {}
    for index in range(len(reader.rows)):
        key = _group_key(reader, index, item, qualifiers)
        if key not in out:
            out[key] = ([], reader.text(index, item).strip())
        out[key][0].append(index)
    return out


def _ordered_by_quantity(reader: Reader, indices: list[int], quantity: Column):
    """Rows of one group in ascending quantity, and what was left out.

    A tier table's last band routinely prints no upper bound, because it has
    none. When exactly one row in a group leaves the quantity blank and it is
    the last row as printed, it is read as that open-ended top band. Any other
    blank leaves the row's place in the order unestablished, so it is set
    aside and counted rather than guessed at.
    """
    numbered = []
    blanks = []
    for index in indices:
        printed = reader.number(index, quantity)
        if printed is None:
            blanks.append(index)
        else:
            numbered.append((printed.value, index))
    numbered.sort(key=lambda pair: pair[0])
    ordered = [index for _, index in numbered]
    set_aside = []
    if len(blanks) == 1 and blanks[0] == indices[-1] and ordered:
        ordered.append(blanks[0])
    else:
        set_aside = blanks
    return ordered, set_aside


def _price_of(reader: Reader, index: int, price: Column, adjustment: Column | None):
    printed = reader.number(index, price)
    if printed is None:
        return None, None
    total = printed.value
    added = None
    if adjustment is not None:
        extra = reader.number(index, adjustment)
        if extra is not None:
            total += extra.value
            added = extra
    return total, (printed, added)


def volume_tier(reader: Reader) -> CheckRun:
    name = "volume-tier"
    quantity = reader.first_usable("quantity")
    price = reader.first_usable("unit_price", "net_price", "list_price")
    if quantity is None:
        return CheckRun(name, False, "no column names a quantity or a volume band")
    if price is None:
        return CheckRun(name, False, "no column names a price")
    if reader.conventions.get(quantity.index) is None:
        return CheckRun(name, False, reader.unreadable(quantity))
    if reader.conventions.get(price.index) is None:
        return CheckRun(name, False, reader.unreadable(price))

    adjustment = reader.first("adjustment")
    item = reader.first("item")
    qualifiers = reader.by_role("qualifier")
    findings: list[Finding] = []
    set_aside: list[str] = []
    compared = 0
    for key, (indices, shown) in _groups(reader, item, qualifiers).items():
        if len(indices) < 2:
            continue
        ordered, blanks = _ordered_by_quantity(reader, indices, quantity)
        if blanks:
            set_aside.append(
                f"{len(blanks)} row(s) in '{shown or reader.sheet}' leave "
                f"'{quantity.label}' blank somewhere other than a single last "
                "row, so where they sit in the order is not established"
            )
        for lower, higher in zip(ordered, ordered[1:]):
            low_price, low_parts = _price_of(reader, lower, price, adjustment)
            high_price, high_parts = _price_of(reader, higher, price, adjustment)
            if low_price is None or high_price is None:
                continue
            compared += 1
            if high_price <= low_price:
                continue
            low_qty = reader.text(lower, quantity).strip() or "(no upper bound printed)"
            high_qty = reader.text(higher, quantity).strip() or "(no upper bound printed)"
            what = f"'{shown}' " if shown else ""
            detail = [
                f"row {reader.line(lower)}: {quantity.label} {low_qty}, "
                f"{price.label} {low_parts[0].text}"
                + (f" + {adjustment.label} {low_parts[1].text}" if low_parts[1] else ""),
                f"row {reader.line(higher)}: {quantity.label} {high_qty}, "
                f"{price.label} {high_parts[0].text}"
                + (f" + {adjustment.label} {high_parts[1].text}" if high_parts[1] else ""),
            ]
            # Both notes can be true of one finding, so they are collected
            # rather than assigned: the second used to overwrite the first.
            notes = []
            if price.role != "unit_price":
                notes.append(
                    f"'{price.label}' was read as the price because no column names a "
                    "unit price. Whether it holds the price of one unit or the total "
                    "for the whole quantity is not something this document states"
                )
            # Tested on the printed rate, not on the rate plus its adjuster.
            # A band printed at 0 with an adjuster of -1.4 sums to -1.4 and was
            # missed by an earlier version of this rule, so the one finding in
            # the audit sample that most needed the note did not carry it.
            if low_parts[0].value == 0:
                notes.append(
                    "the smaller band is priced at zero, which a price list often "
                    "uses for an allowance included in a fixed charge rather than "
                    "for a price of nothing"
                )
            note = "; also, ".join(notes)
            findings.append(
                Finding(
                    check=name,
                    statement=(
                        f"{what}has a {price.label} of {high_parts[0].text} at "
                        f"{quantity.label} {high_qty}, and {low_parts[0].text} at "
                        f"{quantity.label} {low_qty}"
                    ),
                    places=(reader.place(lower, price), reader.place(higher, price)),
                    detail=tuple(detail),
                    note=note,
                )
            )
    run = CheckRun(
        name, True, f"read '{quantity.label}' against '{price.label}'", findings
    )
    run.set_aside = set_aside
    run.comparisons = compared
    return run


def discount_tier(reader: Reader) -> CheckRun:
    name = "discount-tier"
    quantity = reader.first_usable("quantity")
    discount = reader.first_usable("discount_percent")
    if quantity is None:
        return CheckRun(name, False, "no column names a quantity or a volume band")
    if discount is None:
        return CheckRun(name, False, "no column names a discount percentage")
    if reader.conventions.get(discount.index) is None:
        return CheckRun(name, False, reader.unreadable(discount))
    if reader.conventions.get(quantity.index) is None:
        return CheckRun(name, False, reader.unreadable(quantity))

    item = reader.first("item")
    qualifiers = reader.by_role("qualifier")
    findings: list[Finding] = []
    compared = 0
    for key, (indices, shown) in _groups(reader, item, qualifiers).items():
        if len(indices) < 2:
            continue
        ordered, _ = _ordered_by_quantity(reader, indices, quantity)
        for lower, higher in zip(ordered, ordered[1:]):
            low = reader.number(lower, discount)
            high = reader.number(higher, discount)
            if low is None or high is None:
                continue
            compared += 1
            if high.value >= low.value:
                continue
            what = f"'{shown}' " if shown else ""
            findings.append(
                Finding(
                    check=name,
                    statement=(
                        f"{what}has a {discount.label} of {high.text} at "
                        f"{quantity.label} "
                        f"{reader.text(higher, quantity).strip() or '(no bound printed)'}, "
                        f"and {low.text} at {quantity.label} "
                        f"{reader.text(lower, quantity).strip() or '(no bound printed)'}"
                    ),
                    places=(reader.place(lower, discount), reader.place(higher, discount)),
                    detail=(
                        f"row {reader.line(lower)}: {quantity.label} "
                        f"{reader.text(lower, quantity).strip()}, {discount.label} {low.text}",
                        f"row {reader.line(higher)}: {quantity.label} "
                        f"{reader.text(higher, quantity).strip()}, {discount.label} {high.text}",
                    ),
                )
            )
    run = CheckRun(
        name, True, f"read '{quantity.label}' against '{discount.label}'", findings
    )
    run.comparisons = compared
    return run


def _split_components(text: str) -> list[str]:
    for separator in (";", "|", "+", ","):
        if separator in text:
            return [part.strip() for part in text.split(separator) if part.strip()]
    return [text.strip()] if text.strip() else []


def bundle_above_parts(reader: Reader) -> CheckRun:
    name = "bundle-above-parts"
    components = reader.first("components")
    item = reader.first("item")
    price = reader.first_usable("net_price", "unit_price", "list_price")
    if components is None:
        return CheckRun(
            name, False,
            "no column names the items a bundle is made of, so no composition is "
            "stated in this document",
        )
    if item is None:
        return CheckRun(name, False, "no column names the item, so a component cannot be looked up")
    if price is None:
        return CheckRun(name, False, "no column names a price")
    if reader.conventions.get(price.index) is None:
        return CheckRun(name, False, reader.unreadable(price))

    prices: dict[str, tuple[Decimal, int]] = {}
    for index in range(len(reader.rows)):
        key = reader.text(index, item).strip().casefold()
        printed = reader.number(index, price)
        if key and printed is not None and key not in prices:
            prices[key] = (printed.value, index)

    findings: list[Finding] = []
    set_aside: list[str] = []
    compared = 0
    for index in range(len(reader.rows)):
        listed = _split_components(reader.text(index, components))
        if len(listed) < 2:
            continue
        bundle = reader.number(index, price)
        if bundle is None:
            continue
        total = Decimal(0)
        missing = []
        places = [reader.place(index, price)]
        parts = []
        for part in listed:
            found = prices.get(part.strip().casefold())
            if found is None:
                missing.append(part)
                continue
            total += found[0]
            parts.append(f"{part} at {reader.text(found[1], price).strip()}")
            places.append(reader.place(found[1], price))
        if missing:
            set_aside.append(
                f"row {reader.line(index)} names {len(missing)} component(s) this "
                f"document does not price ({', '.join(missing[:3])}"
                f"{'…' if len(missing) > 3 else ''}), so its total is not established"
            )
            continue
        compared += 1
        if bundle.value <= total:
            continue
        findings.append(
            Finding(
                check=name,
                statement=(
                    f"'{reader.text(index, item).strip()}' is priced at {bundle.text}, "
                    f"and the {len(parts)} items this row says it contains are priced "
                    f"at {total} in the same document"
                ),
                places=tuple(places),
                detail=tuple(parts),
            )
        )
    run = CheckRun(
        name, True, f"read '{components.label}' against '{price.label}'", findings
    )
    run.set_aside = set_aside
    run.comparisons = compared
    return run


def _families(columns: list[Column]) -> dict[str, list[Column]]:
    out: dict[str, list[Column]] = {}
    for column in columns:
        out.setdefault(column.family, []).append(column)
    return out


def _nearest(target: Column, candidates: list[Column]) -> Column:
    """The candidate whose name shares the longest run of leading words.

    A published schema writes a percentage and the dollar amount it produces
    as ``standard_charge|negotiated_percentage`` and
    ``standard_charge|negotiated_dollar``, and puts an unrelated
    ``standard_charge|discounted_cash`` beside them. All three share a family.
    Word-prefix length is what separates them: the first two share three
    leading words, the third shares two.

    Pairing the percentage with the cash price instead produced 363,426
    findings across ten real files, every one of them a comparison between two
    numbers that were never meant to agree.
    """
    words = fold(target.name).split()
    best, score = candidates[0], -1
    for candidate in candidates:
        other = fold(candidate.name).split()
        shared = 0
        for left, right in zip(words, other):
            if left != right:
                break
            shared += 1
        if shared > score:
            best, score = candidate, shared
    return best


def _pairable(percent_column: Column, candidates: list[Column]) -> list[Column]:
    """The net-price columns a percentage may legitimately be compared against.

    One candidate: it, because there is nothing to choose between.

    Several: only those whose name is this one's with the last word changed —
    ``…|negotiated_percentage`` and ``…|negotiated_dollar``. A published file
    puts a cash price beside those two, and a gross charge times a negotiated
    percentage has no reason whatever to equal a cash price. Where the
    negotiated dollar column is empty throughout a file, falling back to the
    cash price produced a finding on every row of it.

    None qualifying means the percentage cannot be placed, and the check says
    so rather than comparing it with whatever is nearest.
    """
    if len(candidates) == 1:
        return candidates
    words = fold(percent_column.name).split()
    return [
        column for column in candidates
        if (lambda other: len(other) == len(words) and other[:-1] == words[:-1])(
            fold(column.name).split()
        )
    ]


def stated_discount(reader: Reader) -> CheckRun:
    """Does the percentage printed beside two prices produce the second from the first?

    Two readings of a percentage exist and they are opposites: *20% off* and
    *pays 20% of*. They are told apart by the column's name and never by which
    one happens to reconcile — picking the reading that fits would mean this
    check could never fail.
    """
    name = "stated-discount"
    listed = reader.by_role("list_price")
    nets = reader.by_role("net_price")
    discounts = reader.by_role("discount_percent")
    shares = reader.by_role("percent_of_list")
    if not listed:
        return CheckRun(name, False, "no column names a list price")
    if not nets:
        return CheckRun(name, False, "no column names a net price")
    if not discounts and not shares:
        return CheckRun(
            name, False,
            "no column names a discount percentage or a percentage of the list price",
        )

    net_by_family = _families(nets)
    list_by_family = _families(listed)
    findings: list[Finding] = []
    compared = 0
    pairs = []
    for percent_column, is_discount in [(c, True) for c in discounts] + [
        (c, False) for c in shares
    ]:
        family_nets = net_by_family.get(percent_column.family) or nets
        family_lists = list_by_family.get(percent_column.family) or listed
        pairs.append((family_lists, family_nets, percent_column, is_discount))

    usable = []
    refused = []
    for candidate_lists, candidate_nets, percent_column, is_discount in pairs:
        readable_lists = [
            c for c in candidate_lists if reader.conventions.get(c.index) is not None
        ]
        # The pairing is decided against every net column the document has,
        # and only then filtered to the readable ones. Deciding it against the
        # readable subset first would let an empty negotiated-dollar column
        # leave a cash price as the only candidate — which is exactly the
        # comparison this rule exists to refuse.
        pairable = _pairable(percent_column, candidate_nets)
        readable_nets = [
            c for c in pairable if reader.conventions.get(c.index) is not None
        ]
        if reader.conventions.get(percent_column.index) is None:
            refused.append(reader.unreadable(percent_column))
        elif not readable_lists:
            refused.append(reader.unreadable(candidate_lists[0]))
        elif not readable_nets:
            refused.append(
                f"'{percent_column.label}' could not be placed against any of the "
                f"{len(candidate_nets)} net price column(s) here"
                + (
                    ": none of them is this column's name with the last word "
                    "changed, and a percentage compared with an unrelated price "
                    "is not a comparison"
                    if not pairable else
                    f": the {len(pairable)} that could be paired with it hold no "
                    "number this tool could use"
                )
            )
        else:
            usable.append((readable_lists, readable_nets, percent_column, is_discount))
    if not usable:
        # A wide file can carry hundreds of payer blocks and have every one of
        # them empty. That is a check that could not run, and it says which
        # column stopped it rather than "could not be read".
        return CheckRun(name, False, refused[0] if refused else
                        "no percentage column could be paired with a price")

    for candidate_lists, candidate_nets, percent_column, is_discount in usable:
        chosen_list = _nearest(percent_column, candidate_lists)
        chosen_net = _nearest(percent_column, candidate_nets)
        for index in range(len(reader.rows)):
            percent = reader.number(index, percent_column)
            if percent is None:
                continue
            share = (
                (Decimal(100) - percent.value) if is_discount else percent.value
            ) / Decimal(100)

            # Every candidate pair is tried, and a finding is reported only
            # when NONE of them reconciles. Binding to the nearest name alone
            # reported a contradiction in a document that held a perfectly
            # consistent reading two columns to the right, and reordering the
            # two columns made the finding disappear.
            reconciled = False
            attempted = None
            for list_column in candidate_lists:
                gross = reader.number(index, list_column)
                if gross is None or gross.value == 0:
                    continue
                implied = gross.value * share
                for net_column in candidate_nets:
                    net = reader.number(index, net_column)
                    if net is None:
                        continue
                    tolerance = (
                        net.tolerance()
                        + gross.tolerance() * abs(share)
                        + abs(gross.value) * percent.tolerance() / Decimal(100)
                    )
                    if attempted is None or (
                        list_column is chosen_list and net_column is chosen_net
                    ):
                        attempted = (gross, net, implied, tolerance,
                                     list_column, net_column)
                    if abs(implied - net.value) <= tolerance:
                        reconciled = True
                        break
                if reconciled:
                    break
            if attempted is None:
                continue
            compared += 1
            if reconciled:
                continue
            gross, net, implied, tolerance, list_column, net_column = attempted
            reading = (
                f"{percent.text} off {gross.text}" if is_discount
                else f"{percent.text} of {gross.text}"
            )
            tried = ""
            if len(candidate_lists) > 1 or len(candidate_nets) > 1:
                tried = (
                    f"no pairing of the {len(candidate_lists)} list price and "
                    f"{len(candidate_nets)} net price column(s) in this row "
                    "reconciles"
                )
            findings.append(
                Finding(
                    check=name,
                    statement=(
                        f"row {reader.line(index)} prints {reading}, which is "
                        f"{implied.quantize(Decimal(1).scaleb(-max(net.decimals, 2)))}, "
                        f"beside a {net_column.label} of {net.text}"
                    ),
                    places=(
                        reader.place(index, list_column),
                        reader.place(index, percent_column),
                        reader.place(index, net_column),
                    ),
                    detail=tuple(
                        x for x in (
                            f"{list_column.label} {gross.text}",
                            f"{percent_column.label} {percent.text}"
                            + ("  (read as a discount off the list price)" if is_discount
                               else "  (read as a percentage of the list price)"),
                            f"{net_column.label} {net.text}",
                            f"allowed for rounding: ±{tolerance.normalize()}",
                            tried,
                        ) if x
                    ),
                )
            )
    run = CheckRun(
        name, True,
        f"read {len(usable)} percentage column(s) against the prices beside them"
        + (f"; {len(refused)} could not be used" if refused else ""),
        findings,
    )
    run.set_aside = refused
    run.comparisons = compared
    return run


def two_prices(reader: Reader) -> CheckRun:
    name = "two-prices"
    item = reader.first("item")
    price = reader.first_usable("net_price", "unit_price", "list_price")
    if item is None:
        return CheckRun(name, False, "no column names the item being priced")
    if price is None:
        return CheckRun(name, False, "no column names a price")
    if reader.conventions.get(price.index) is None:
        return CheckRun(name, False, reader.unreadable(price))

    # Everything that could legitimately make two rows different prices is part
    # of the identity. A tool that ignored the quantity column would report
    # every tier table as pricing the same item twice.
    # Every column naming what is priced counts, not only the first. A file
    # that prints a description and a code prices two different codes that
    # share a description, and holding only the description equal reported
    # 75,968 of those as one item at two prices.
    identity = (
        [c for c in reader.by_role("item") if c is not item]
        + reader.by_role("qualifier")
        + reader.by_role("quantity")
        + reader.by_role("unit")
        + reader.by_role("currency")
    )
    seen: dict[tuple, tuple[int, Decimal, str]] = {}
    findings: list[Finding] = []
    compared = 0
    for index in range(len(reader.rows)):
        key_item = reader.text(index, item).strip()
        if not key_item:
            continue
        printed = reader.number(index, price)
        if printed is None:
            continue
        key = (key_item.casefold(),) + tuple(
            reader.text(index, column).strip().casefold() for column in identity
        )
        if key not in seen:
            seen[key] = (index, printed.value, printed.text)
            continue
        first_index, first_value, first_text = seen[key]
        compared += 1
        if first_value == printed.value:
            continue
        told_apart = ", ".join(
            f"{column.label} {reader.text(index, column).strip()}"
            for column in identity
            if reader.text(index, column).strip()
        )
        # Never "no column tells them apart" — a column this tool has no name
        # for may well tell them apart, and saying otherwise states as fact
        # something the tool cannot know.
        findings.append(
            Finding(
                check=name,
                statement=(
                    f"'{key_item}' is priced at {first_text} on row "
                    f"{reader.line(first_index)} and at {printed.text} on row "
                    f"{reader.line(index)}"
                ),
                places=(
                    reader.place(first_index, price),
                    reader.place(index, price),
                ),
                detail=(
                    (f"the two rows agree on: {told_apart}" if told_apart
                     else "no other column this tool recognises tells the two "
                          "rows apart; one it does not recognise may"),
                ),
            )
        )
    run = CheckRun(
        name, True,
        f"read '{item.label}' against '{price.label}'"
        + (f", holding {len(identity)} other column(s) equal" if identity else ""),
        findings,
    )
    run.comparisons = compared
    return run


def inverted_range(reader: Reader) -> CheckRun:
    name = "inverted-range"
    minimums = reader.by_role("minimum")
    maximums = reader.by_role("maximum")
    if not minimums:
        return CheckRun(name, False, "no column names the bottom of a range")
    if not maximums:
        return CheckRun(name, False, "no column names the top of a range")

    by_family = _families(maximums)
    pairs = []
    for low in minimums:
        candidates = by_family.get(low.family) or maximums
        pairs.append((low, _nearest(low, candidates)))

    findings: list[Finding] = []
    refused: list[str] = []
    compared = 0
    for low, high in pairs:
        bad = [c for c in (low, high) if reader.conventions.get(c.index) is None]
        if bad:
            refused.append(reader.unreadable(bad[0]))
            continue
        for index in range(len(reader.rows)):
            bottom = reader.number(index, low)
            top = reader.number(index, high)
            if bottom is None or top is None:
                continue
            compared += 1
            if bottom.value <= top.value:
                continue
            findings.append(
                Finding(
                    check=name,
                    statement=(
                        f"row {reader.line(index)} states a {low.label} of "
                        f"{bottom.text} and a {high.label} of {top.text}"
                    ),
                    places=(reader.place(index, low), reader.place(index, high)),
                )
            )
    if not pairs:
        return CheckRun(name, False, "no minimum could be paired with a maximum")
    if len(refused) == len(pairs):
        return CheckRun(name, False, refused[0])
    run = CheckRun(
        name, True,
        f"read {len(pairs) - len(refused)} minimum/maximum pair(s)"
        + (f"; {len(refused)} could not be used" if refused else ""),
        findings,
    )
    run.set_aside = refused
    run.comparisons = compared
    return run


def unit_mismatch(reader: Reader) -> CheckRun:
    """One item, two units or two currencies, in the same document.

    A price list covering several currencies is a normal thing and is not
    reported. What is reported is one item priced in two of them, because the
    document then says two different things about the same item.
    """
    name = "unit-mismatch"
    item = reader.first("item")
    unit = reader.first("unit")
    currency = reader.first("currency")
    if item is None:
        return CheckRun(name, False, "no column names the item being priced")
    if unit is None and currency is None:
        return CheckRun(name, False, "no column names a unit of measure or a currency")

    # Qualifiers are held equal, exactly as in two-prices. A price list that
    # quotes one product in GBP for the UK and EUR for the EU is a normal
    # document, and reporting it was this check's first behaviour.
    qualifiers = (
        [c for c in reader.by_role("item") if c is not item]
        + reader.by_role("qualifier")
        + reader.by_role("quantity")
    )
    plural = {"unit": "units", "currency": "currencies"}
    findings: list[Finding] = []
    for column, what in ((unit, "unit"), (currency, "currency")):
        if column is None:
            continue
        seen: dict[tuple, tuple[dict[str, int], str]] = {}
        for index in range(len(reader.rows)):
            key = reader.text(index, item).strip()
            value = reader.text(index, column).strip()
            if not key or is_blank(value):
                continue
            group = (key.casefold(),) + tuple(
                reader.text(index, q).strip().casefold() for q in qualifiers
            )
            if group not in seen:
                seen[group] = ({}, key)
            seen[group][0].setdefault(value, index)
        for group, (values, shown) in seen.items():
            if len(values) < 2:
                continue
            listed = sorted(values.items(), key=lambda pair: pair[1])
            held = ", ".join(
                f"{q.label} {reader.text(listed[0][1], q).strip()}"
                for q in qualifiers
                if reader.text(listed[0][1], q).strip()
            )
            findings.append(
                Finding(
                    check=name,
                    statement=(
                        f"'{shown}' is priced in {len(values)} different "
                        f"{plural[what]} in this document: "
                        + ", ".join(f"{value} (row {reader.line(row)})" for value, row in listed)
                    ),
                    places=tuple(reader.place(row, column) for _, row in listed),
                    detail=((f"the rows agree on: {held}",) if held else ()),
                )
            )
    looked_at = ", ".join(
        f"'{c.label}'" for c in (unit, currency) if c is not None
    )
    # No `comparisons`: this check compares text, and exit 0 is earned by
    # arithmetic. Saying so in the reason keeps "0 comparison(s)" from reading
    # as "did nothing".
    return CheckRun(
        name, True,
        f"read {looked_at} against '{item.label}'"
        + (f", holding {len(qualifiers)} other column(s) equal" if qualifiers else "")
        + " (compares text, not numbers)",
        findings,
    )


RUNNERS = {
    "volume-tier": volume_tier,
    "discount-tier": discount_tier,
    "bundle-above-parts": bundle_above_parts,
    "stated-discount": stated_discount,
    "two-prices": two_prices,
    "inverted-range": inverted_range,
    "unit-mismatch": unit_mismatch,
}
