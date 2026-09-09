"""Each check, shown finding what it is for and shown not finding what it is not."""

import tempfile
import unittest
from pathlib import Path

from adds_up.analyse import analyse


def run(text: str, **kwargs):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "list.csv"
        path.write_text(text, encoding="utf-8")
        return analyse(path, **kwargs)


def check(result, name):
    return next(c for c in result.tables[0].checks if c.name == name)


def statements(result, name):
    return [f.statement for f in check(result, name).findings]


class VolumeTier(unittest.TestCase):
    DECLINING = (
        "SKU,Quantity,Unit price\n"
        "A,1,10.00\nA,10,9.00\nA,100,8.00\n"
    )
    INVERTED = (
        "SKU,Quantity,Unit price\n"
        "A,1,10.00\nA,10,9.00\nA,100,9.50\n"
    )

    def test_a_declining_ladder_is_not_a_finding(self):
        self.assertEqual(statements(run(self.DECLINING), "volume-tier"), [])

    def test_a_larger_quantity_costing_more_is_a_finding(self):
        found = statements(run(self.INVERTED), "volume-tier")
        self.assertEqual(len(found), 1)
        self.assertIn("9.50", found[0])
        self.assertIn("9.00", found[0])

    def test_rows_out_of_printed_order_are_still_ordered_by_quantity(self):
        scrambled = "SKU,Quantity,Unit price\nA,100,9.50\nA,1,10.00\nA,10,9.00\n"
        self.assertEqual(len(statements(run(scrambled), "volume-tier")), 1)

    def test_two_items_do_not_contaminate_each_other(self):
        two = (
            "SKU,Quantity,Unit price\n"
            "A,1,10.00\nA,100,8.00\n"
            "B,1,3.00\nB,100,2.00\n"
        )
        self.assertEqual(statements(run(two), "volume-tier"), [])

    def test_an_open_ended_top_band_is_read_as_the_top(self):
        """A tier table's last row routinely prints no upper bound."""
        text = "tier,max,rate\n1,700,0.09\n2,1200,0.08\n3,,0.07\n"
        self.assertEqual(statements(run(text), "volume-tier"), [])

    def test_an_open_ended_top_band_that_costs_more_is_found(self):
        text = "tier,max,rate\n1,700,0.09\n2,1200,0.08\n3,,0.085\n"
        self.assertEqual(len(statements(run(text), "volume-tier")), 1)

    def test_more_than_one_blank_quantity_is_set_aside_not_guessed(self):
        text = "max,rate\n700,0.09\n,0.08\n,0.10\n"
        run_result = check(run(text), "volume-tier")
        self.assertTrue(run_result.set_aside)
        self.assertIn("not established", run_result.set_aside[0])

    def test_the_leftmost_quantity_column_is_the_one_used(self):
        """A tier table often prints both an ordinal and a threshold.

        Both are quantities. The leftmost is used, and the report names it, so
        which one was read is never a thing a reader has to work out.
        """
        text = "tier,max,rate\n1,700,0.09\n2,1200,0.08\n3,,0.07\n"
        self.assertIn("'tier'", check(run(text), "volume-tier").reason)

    def test_an_adjustment_column_is_added_to_the_rate(self):
        """0.05+0.04 is above 0.08+0.00, and only the sum shows it."""
        text = "tier,max,rate,adj\n1,700,0.08,0.00\n2,,0.05,0.04\n"
        self.assertEqual(len(statements(run(text), "volume-tier")), 1)

    def test_a_zero_priced_lower_band_is_reported_with_a_note(self):
        text = "tier,max,rate\n1,500,0.00\n2,,0.10\n"
        findings = check(run(text), "volume-tier").findings
        self.assertEqual(len(findings), 1)
        self.assertIn("allowance", findings[0].note)

    def test_it_does_not_run_without_a_quantity(self):
        run_result = check(run("SKU,Unit price\nA,10.00\nB,9.00\n"), "volume-tier")
        self.assertFalse(run_result.ran)
        self.assertIn("quantity", run_result.reason)


class ChoosingAColumn(unittest.TestCase):
    """Several columns can claim one role, and only some hold numbers."""

    def test_an_empty_price_column_does_not_block_a_usable_one(self):
        """The shape a real published file comes in.

        A standard-charges file carries a cash price and a negotiated price
        side by side, and a hospital that publishes only the second leaves the
        first empty on every row. Taking the leftmost regardless reported that
        the check could not run.
        """
        text = (
            "Item,Quantity,discounted cash,negotiated dollar\n"
            "A,1,,10.00\nA,10,,11.00\n"
        )
        run_result = check(run(text), "volume-tier")
        self.assertTrue(run_result.ran, run_result.reason)
        self.assertIn("negotiated dollar", run_result.reason)
        self.assertEqual(len(run_result.findings), 1)

    def test_when_no_column_in_the_role_is_readable_it_says_which(self):
        text = "Item,Quantity,Net price\nA,1,call us\nA,10,ask\n"
        run_result = check(run(text), "volume-tier")
        self.assertFalse(run_result.ran)
        self.assertIn("Net price", run_result.reason)
        self.assertIn("holds no number", run_result.reason)


class DiscountTier(unittest.TestCase):
    def test_a_growing_discount_is_not_a_finding(self):
        text = "SKU,Quantity,Discount %\nA,1,0\nA,10,5\nA,100,10\n"
        self.assertEqual(statements(run(text), "discount-tier"), [])

    def test_a_shrinking_discount_is_a_finding(self):
        text = "SKU,Quantity,Discount %\nA,1,0\nA,10,12\nA,100,8\n"
        self.assertEqual(len(statements(run(text), "discount-tier")), 1)

    def test_it_does_not_run_without_a_discount_column(self):
        run_result = check(run("SKU,Quantity,Price\nA,1,10\nA,2,9\n"), "discount-tier")
        self.assertFalse(run_result.ran)


class StatedDiscount(unittest.TestCase):
    def test_a_discount_that_reconciles_is_not_a_finding(self):
        text = "Item,List price,Discount %,Net price\nA,100.00,10,90.00\n"
        self.assertEqual(statements(run(text), "stated-discount"), [])

    def test_a_discount_that_does_not_reconcile_is_a_finding(self):
        text = "Item,List price,Discount %,Net price\nA,100.00,10,88.00\n"
        self.assertEqual(len(statements(run(text), "stated-discount")), 1)

    def test_rounding_within_the_printed_precision_is_not_a_finding(self):
        """33.33% off 100.00 is 66.67, and the document printed both."""
        text = "Item,List price,Discount %,Net price\nA,100.00,33.33,66.67\n"
        self.assertEqual(statements(run(text), "stated-discount"), [])

    def test_a_percentage_of_the_list_is_read_the_other_way_round(self):
        """`negotiated percentage` means *pays 30% of*, not *30% off*.

        Reading it as a discount would call the correct row a contradiction
        and the contradictory row correct.
        """
        text = "Item,standard_charge|gross,standard_charge|X|Y|negotiated_percentage,standard_charge|X|Y|negotiated_dollar\nA,100.00,30,30.00\n"
        self.assertEqual(statements(run(text), "stated-discount"), [])

    def test_a_percentage_of_the_list_that_does_not_reconcile_is_found(self):
        text = "Item,standard_charge|gross,standard_charge|X|Y|negotiated_percentage,standard_charge|X|Y|negotiated_dollar\nA,100.00,30,70.00\n"
        self.assertEqual(len(statements(run(text), "stated-discount")), 1)

    def test_a_zero_list_price_is_skipped_rather_than_divided_by(self):
        text = "Item,List price,Discount %,Net price\nA,0.00,10,0.00\n"
        self.assertEqual(statements(run(text), "stated-discount"), [])

    def test_it_does_not_run_without_a_list_price(self):
        run_result = check(run("Item,Net price,Discount %\nA,90,10\n"), "stated-discount")
        self.assertFalse(run_result.ran)
        self.assertIn("list price", run_result.reason)


class TwoPrices(unittest.TestCase):
    def test_the_same_item_at_two_prices_is_a_finding(self):
        text = "SKU,Price\nA,10.00\nB,5.00\nA,11.00\n"
        found = statements(run(text), "two-prices")
        self.assertEqual(len(found), 1)
        self.assertIn("10.00", found[0])
        self.assertIn("11.00", found[0])

    def test_the_same_item_at_the_same_price_twice_is_not(self):
        self.assertEqual(statements(run("SKU,Price\nA,10.00\nA,10.00\n"), "two-prices"), [])

    def test_a_tier_table_is_not_the_same_item_priced_twice(self):
        """Without this, every volume price list is one long finding."""
        text = "SKU,Quantity,Price\nA,1,10.00\nA,10,9.00\nA,100,8.00\n"
        self.assertEqual(statements(run(text), "two-prices"), [])

    def test_a_qualifier_column_tells_two_rows_apart(self):
        text = "SKU,Region,Price\nA,UK,10.00\nA,US,12.00\n"
        self.assertEqual(statements(run(text), "two-prices"), [])

    def test_the_finding_says_what_the_rows_agreed_on(self):
        text = "SKU,Region,Price\nA,UK,10.00\nA,UK,12.00\n"
        findings = check(run(text), "two-prices").findings
        self.assertEqual(len(findings), 1)
        self.assertIn("Region UK", findings[0].detail[0])


class InvertedRange(unittest.TestCase):
    def test_a_minimum_above_its_maximum_is_a_finding(self):
        text = "Item,Min charge,Max charge\nA,400,300\n"
        self.assertEqual(len(statements(run(text), "inverted-range")), 1)

    def test_a_minimum_below_its_maximum_is_not(self):
        self.assertEqual(
            statements(run("Item,Min charge,Max charge\nA,300,400\n"), "inverted-range"), []
        )

    def test_equal_ends_are_not_a_finding(self):
        self.assertEqual(
            statements(run("Item,Min charge,Max charge\nA,300,300\n"), "inverted-range"), []
        )

    def test_a_blank_end_is_not_a_zero(self):
        self.assertEqual(
            statements(run("Item,Min charge,Max charge\nA,300,\n"), "inverted-range"), []
        )

    def test_families_pair_the_right_min_with_the_right_max(self):
        text = (
            "Item,standard_charge|A|min,standard_charge|A|max,"
            "standard_charge|B|min,standard_charge|B|max\n"
            "X,10,20,90,50\n"
        )
        found = statements(run(text), "inverted-range")
        self.assertEqual(len(found), 1)
        self.assertIn("90", found[0])

    def test_it_does_not_run_with_only_one_end(self):
        run_result = check(run("Item,Min charge\nA,300\n"), "inverted-range")
        self.assertFalse(run_result.ran)


class UnitMismatch(unittest.TestCase):
    def test_one_item_in_two_currencies_is_a_finding(self):
        text = "SKU,Currency,Price\nA,GBP,10\nA,EUR,12\n"
        self.assertEqual(len(statements(run(text), "unit-mismatch")), 1)

    def test_a_document_covering_two_currencies_is_not_a_finding(self):
        """A multi-currency price list is a normal document."""
        text = "SKU,Currency,Price\nA,GBP,10\nB,EUR,12\n"
        self.assertEqual(statements(run(text), "unit-mismatch"), [])

    def test_one_item_in_two_units_is_a_finding(self):
        text = "SKU,UoM,Price\nA,kg,10\nA,litre,12\n"
        self.assertEqual(len(statements(run(text), "unit-mismatch")), 1)

    def test_a_blank_unit_is_not_a_second_unit(self):
        text = "SKU,UoM,Price\nA,kg,10\nA,,12\n"
        self.assertEqual(statements(run(text), "unit-mismatch"), [])


class BundleAboveParts(unittest.TestCase):
    TEXT = (
        "SKU,Contains,Price\n"
        "A,,10.00\n"
        "B,,20.00\n"
        "KIT-1,A;B,35.00\n"
        "KIT-2,A;B,25.00\n"
    )

    def test_a_bundle_above_the_sum_of_its_parts_is_a_finding(self):
        found = statements(run(self.TEXT), "bundle-above-parts")
        self.assertEqual(len(found), 1)
        self.assertIn("KIT-1", found[0])

    def test_a_component_this_document_does_not_price_is_set_aside(self):
        text = "SKU,Contains,Price\nA,,10.00\nKIT,A;Z,50.00\n"
        run_result = check(run(text), "bundle-above-parts")
        self.assertEqual(run_result.findings, [])
        self.assertTrue(run_result.set_aside)
        self.assertIn("not established", run_result.set_aside[0])

    def test_it_does_not_run_without_a_composition(self):
        run_result = check(run("SKU,Price\nA,10\n"), "bundle-above-parts")
        self.assertFalse(run_result.ran)
        self.assertIn("no composition is stated", run_result.reason)


class NothingIsJudged(unittest.TestCase):
    """No finding anywhere says a price is right, wrong, high, low or unfair."""

    FORBIDDEN = (
        "should", "wrong", "incorrect", "error", "mistake", "too high",
        "too low", "unfair", "uncompetitive", "overpriced", "underpriced",
        "margin", "cost of goods", "profit", "loss", "recommend", "fix",
    )

    def test_no_finding_passes_judgement(self):
        text = (
            "SKU,Quantity,List price,Discount %,Net price,Min charge,Max charge,Currency\n"
            "A,1,100.00,10,88.00,400,300,GBP\n"
            "A,10,100.00,5,95.00,400,300,EUR\n"
        )
        result = run(text)
        self.assertTrue(result.findings)
        for finding in result.findings:
            blob = " ".join(
                [finding.statement, finding.note, *finding.detail]
            ).casefold()
            for word in self.FORBIDDEN:
                with self.subTest(word=word, statement=finding.statement):
                    self.assertNotIn(word, blob)


if __name__ == "__main__":
    unittest.main()
