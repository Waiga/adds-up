"""Reading printed numbers, and refusing to when the printing is undecidable."""

import unittest
from decimal import Decimal

from adds_up.numbers import (
    COMMA_DECIMAL,
    DOT_DECIMAL,
    Printed,
    _shape,
    convention_of,
    is_blank,
    parse,
    strip_currency,
)


class Shapes(unittest.TestCase):
    """What the separators in a body of digits can and cannot mean."""

    def test_two_kinds_of_separator_settle_each_other(self):
        self.assertEqual(_shape("1,234.56"), "unambiguous-dot")
        self.assertEqual(_shape("1.234,56"), "unambiguous-comma")

    def test_a_repeated_separator_can_only_be_grouping(self):
        self.assertEqual(_shape("1.234.567"), "unambiguous-comma")
        self.assertEqual(_shape("1,234,567"), "unambiguous-dot")

    def test_a_fraction_that_is_not_three_digits_is_a_fraction(self):
        self.assertEqual(_shape("12.34"), "unambiguous-dot")
        self.assertEqual(_shape("12,3456"), "unambiguous-comma")

    def test_a_leading_zero_cannot_be_a_thousands_group(self):
        """The defect the corpus found.

        1,898 real tariffs price in the shape 0.091 and every one of them was
        refused as undecidable until this rule existed. Nobody writes 0,091 to
        mean ninety-one.
        """
        self.assertEqual(_shape("0.091"), "unambiguous-dot")
        self.assertEqual(_shape("0,091"), "unambiguous-comma")

    def test_more_than_three_digits_in_front_cannot_be_a_group(self):
        self.assertEqual(_shape("1234.567"), "unambiguous-dot")

    def test_the_genuinely_undecidable_case_stays_undecidable(self):
        self.assertEqual(_shape("1.234"), "ambiguous")
        self.assertEqual(_shape("1,234"), "ambiguous")
        self.assertEqual(_shape("100.000"), "ambiguous")


class ColumnConvention(unittest.TestCase):
    def test_one_decisive_cell_settles_the_whole_column(self):
        convention, why = convention_of(["1,234", "5,678", "9.99"])
        self.assertEqual(convention, DOT_DECIMAL)
        self.assertIn("1,234.56", why)

    def test_a_column_of_only_undecidable_cells_is_refused(self):
        convention, why = convention_of(["1,234", "5,678"])
        self.assertIsNone(convention)
        self.assertIn("no other cell", why)

    def test_a_column_that_contradicts_itself_is_refused(self):
        convention, why = convention_of(["1,234.56", "9.876,54"])
        self.assertIsNone(convention)
        self.assertIn("mixes both", why)

    def test_a_column_with_no_separators_at_all_is_read_plainly(self):
        convention, why = convention_of(["10", "20", "30"])
        self.assertEqual(convention, DOT_DECIMAL)
        self.assertIn("no cell", why)

    def test_a_column_of_words_holds_no_number(self):
        convention, why = convention_of(["red", "blue", ""])
        self.assertIsNone(convention)
        self.assertIn("no number", why)

    def test_blanks_do_not_vote(self):
        convention, _ = convention_of(["", "n/a", "-", "1.5"])
        self.assertEqual(convention, DOT_DECIMAL)


class Currency(unittest.TestCase):
    def test_a_leading_symbol_comes_off(self):
        self.assertEqual(strip_currency("$12.50"), ("12.50", "USD"))
        self.assertEqual(strip_currency("€9,90"), ("9,90", "EUR"))

    def test_a_trailing_symbol_comes_off(self):
        self.assertEqual(strip_currency("12,50 €"), ("12,50", "EUR"))

    def test_a_code_beside_the_number_comes_off(self):
        self.assertEqual(strip_currency("USD 12.50"), ("12.50", "USD"))
        self.assertEqual(strip_currency("12.50 GBP"), ("12.50", "GBP"))

    def test_a_bare_number_has_no_currency(self):
        self.assertEqual(strip_currency("12.50"), ("12.50", None))

    def test_a_symbol_alone_is_not_stripped_to_nothing(self):
        self.assertEqual(strip_currency("$"), ("$", None))


class Parsing(unittest.TestCase):
    def test_a_plain_number(self):
        printed = parse("12.50", DOT_DECIMAL)
        self.assertEqual(printed.value, Decimal("12.50"))
        self.assertEqual(printed.decimals, 2)

    def test_grouping_is_removed_and_the_decimal_kept(self):
        printed = parse("1,234.56", DOT_DECIMAL)
        self.assertEqual(printed.value, Decimal("1234.56"))
        printed = parse("1.234,56", COMMA_DECIMAL)
        self.assertEqual(printed.value, Decimal("1234.56"))

    def test_accounting_negatives(self):
        self.assertEqual(parse("(12.50)", DOT_DECIMAL).value, Decimal("-12.50"))
        self.assertEqual(parse("12.50-", DOT_DECIMAL).value, Decimal("-12.50"))
        self.assertEqual(parse("-12.50", DOT_DECIMAL).value, Decimal("-12.50"))

    def test_a_currency_and_a_percent_together(self):
        printed = parse("15.5%", DOT_DECIMAL)
        self.assertTrue(printed.percent)
        self.assertEqual(printed.value, Decimal("15.5"))

    def test_currency_survives_onto_the_result(self):
        self.assertEqual(parse("$12.50", DOT_DECIMAL).currency, "USD")

    def test_thin_and_non_breaking_spaces_as_grouping(self):
        self.assertEqual(parse("1 234,56", COMMA_DECIMAL).value, Decimal("1234.56"))
        self.assertEqual(parse("1 234,56", COMMA_DECIMAL).value, Decimal("1234.56"))

    def test_a_blank_is_not_a_zero(self):
        for text in ("", "  ", "n/a", "N/A", "-", "—", "TBD", "nil", "#N/A"):
            with self.subTest(text=text):
                self.assertIsNone(parse(text, DOT_DECIMAL))
                self.assertTrue(is_blank(text))

    def test_zero_is_a_zero(self):
        printed = parse("0.00", DOT_DECIMAL)
        self.assertIsNotNone(printed)
        self.assertEqual(printed.value, Decimal("0.00"))
        self.assertFalse(is_blank("0.00"))

    def test_words_are_not_numbers(self):
        for text in ("call for price", "POA", "12 each", "see note"):
            with self.subTest(text=text):
                self.assertIsNone(parse(text, DOT_DECIMAL))

    def test_the_original_text_is_kept(self):
        self.assertEqual(parse("$1,234.50", DOT_DECIMAL).text, "$1,234.50")


class Tolerance(unittest.TestCase):
    """A printed number stands for a range, and that range sets the tolerance."""

    def test_two_decimals_allow_half_a_cent(self):
        self.assertEqual(Printed(Decimal("12.34"), 2, "12.34").tolerance(), Decimal("0.005"))

    def test_no_decimals_allow_half_a_unit(self):
        self.assertEqual(Printed(Decimal("12"), 0, "12").tolerance(), Decimal("0.5"))

    def test_more_precision_allows_less(self):
        fine = Printed(Decimal("12.3456"), 4, "12.3456").tolerance()
        coarse = Printed(Decimal("12.34"), 2, "12.34").tolerance()
        self.assertLess(fine, coarse)


if __name__ == "__main__":
    unittest.main()
