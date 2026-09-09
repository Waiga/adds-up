"""Naming columns from what they are called, and refusing when the name is two things."""

import unittest

from adds_up.columns import ROLES, classify, fold, vocabulary_lines


def roles(header, overrides=None):
    return {c.name: c.role for c in classify(header, overrides)}


class Folding(unittest.TestCase):
    def test_punctuation_and_case_are_flattened(self):
        self.assertEqual(fold("Unit_Price"), "unit price")
        self.assertEqual(fold("UNIT-PRICE"), "unit price")
        self.assertEqual(fold("standard_charge|gross"), "standard charge gross")

    def test_a_percent_sign_becomes_a_word(self):
        self.assertEqual(fold("Discount %"), "discount percent")

    def test_whitespace_collapses(self):
        self.assertEqual(fold("  Net   Price  "), "net price")


class KnownNames(unittest.TestCase):
    def test_the_plain_ones(self):
        found = roles(["SKU", "Quantity", "Unit price", "Currency", "UoM"])
        self.assertEqual(found["SKU"], "item")
        self.assertEqual(found["Quantity"], "quantity")
        self.assertEqual(found["Unit price"], "unit_price")
        self.assertEqual(found["Currency"], "currency")
        self.assertEqual(found["UoM"], "unit")

    def test_a_compound_name_is_read_from_its_ending(self):
        """The shape a real published schema uses, without knowing the payer."""
        found = roles([
            "standard_charge|gross",
            "standard_charge|Aetna|PPO|negotiated_dollar",
            "standard_charge|Aetna|PPO|negotiated_percentage",
        ])
        self.assertEqual(found["standard_charge|gross"], "list_price")
        self.assertEqual(found["standard_charge|Aetna|PPO|negotiated_dollar"], "net_price")
        self.assertEqual(
            found["standard_charge|Aetna|PPO|negotiated_percentage"], "percent_of_list"
        )

    def test_a_compound_name_keeps_the_family_that_pairs_it(self):
        columns = {c.name: c for c in classify([
            "standard_charge|Aetna|PPO|negotiated_dollar",
            "standard_charge|Cigna|HMO|negotiated_percentage",
        ])}
        self.assertEqual(columns["standard_charge|Aetna|PPO|negotiated_dollar"].family, "aetna ppo")
        self.assertEqual(
            columns["standard_charge|Cigna|HMO|negotiated_percentage"].family, "cigna hmo"
        )

    def test_a_percentage_off_and_a_percentage_of_are_different_roles(self):
        """They are opposites, and only the name tells them apart."""
        found = roles(["Discount %", "Negotiated percentage"])
        self.assertEqual(found["Discount %"], "discount_percent")
        self.assertEqual(found["Negotiated percentage"], "percent_of_list")

    def test_an_unknown_name_gets_no_role_and_says_so(self):
        column = classify(["Wibble factor"])[0]
        self.assertIsNone(column.role)
        self.assertIn("not a name this tool knows", column.reason)

    def test_an_empty_heading_gets_no_role(self):
        column = classify([""])[0]
        self.assertIsNone(column.role)
        self.assertIn("no heading", column.reason)


class BoundsAreSettledByTheRestOfTheTable(unittest.TestCase):
    """``max`` is a band top in one price list and a price ceiling in another."""

    def test_a_max_with_no_min_beside_it_is_a_quantity_band(self):
        found = roles(["tier", "max", "rate"])
        self.assertEqual(found["max"], "quantity")

    def test_a_max_with_a_min_beside_it_is_a_range(self):
        found = roles(["code", "min", "max", "price"])
        self.assertEqual(found["min"], "minimum")
        self.assertEqual(found["max"], "maximum")

    def test_the_reason_says_which_way_it_went(self):
        column = {c.name: c for c in classify(["tier", "max", "rate"])}["max"]
        self.assertIn("not read as one", column.reason)

    def test_from_and_to_are_always_quantity(self):
        found = roles(["Item", "From", "To", "Price"])
        self.assertEqual(found["From"], "quantity")
        self.assertEqual(found["To"], "quantity")


class Ambiguity(unittest.TestCase):
    def test_a_qualifier_is_recognised_as_one(self):
        found = roles(["SKU", "Region", "Price"])
        self.assertEqual(found["Region"], "qualifier")

    def test_a_trailing_qualifier_word_counts(self):
        found = roles(["SKU", "Customer group", "Price"])
        self.assertEqual(found["Customer group"], "qualifier")


class Overrides(unittest.TestCase):
    def test_map_by_position_wins(self):
        found = roles(["Wibble", "Price"], overrides={0: "item"})
        self.assertEqual(found["Wibble"], "item")

    def test_an_override_says_it_was_an_override(self):
        column = classify(["Wibble"], overrides={0: "item"})[0]
        self.assertIn("--map", column.reason)

    def test_an_override_survives_the_bound_reconciliation(self):
        found = roles(["min", "max"], overrides={1: "quantity"})
        self.assertEqual(found["max"], "quantity")


class Vocabulary(unittest.TestCase):
    def test_every_role_appears_in_the_printed_vocabulary(self):
        printed = "\n".join(vocabulary_lines())
        for role in ROLES:
            with self.subTest(role=role):
                self.assertIn(role, printed)

    def test_the_vocabulary_is_not_empty(self):
        self.assertGreater(len(vocabulary_lines()), 60)


if __name__ == "__main__":
    unittest.main()
