"""The command line, and above all its exit codes.

Exit 0 has to mean *checks ran and found nothing*. A run in which nothing was
compared must never reach it, because a green build over a price list nothing
was checked in is the single outcome this tool exists not to produce.
"""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from adds_up.checks import CHECK_NAMES
from adds_up.cli import main

CLEAN = "SKU,Quantity,Unit price\nA,1,10.00\nA,10,9.00\n"
DIRTY = "SKU,Quantity,Unit price\nA,1,10.00\nA,10,11.00\n"


def temp(name: str, text: str) -> Path:
    path = Path(tempfile.mkdtemp()) / name
    path.write_text(text, encoding="utf-8")
    return path


def call(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class ExitCodes(unittest.TestCase):
    def test_nothing_found_is_zero(self):
        code, _, _ = call(str(temp("a.csv", CLEAN)))
        self.assertEqual(code, 0)

    def test_a_finding_is_one(self):
        code, _, _ = call(str(temp("a.csv", DIRTY)))
        self.assertEqual(code, 1)

    def test_a_missing_file_is_two(self):
        code, _, err = call("/no/such/file.csv")
        self.assertEqual(code, 2)
        self.assertIn("does not exist", err)

    def test_a_file_that_cannot_be_read_is_two(self):
        code, _, err = call(str(temp("a.pdf", "x")))
        self.assertEqual(code, 2)

    def test_every_check_switched_off_is_two_not_zero(self):
        argv = [str(temp("a.csv", CLEAN))]
        for name in CHECK_NAMES:
            argv += ["--skip", name]
        code, out, err = call(*argv)
        self.assertEqual(code, 2)
        self.assertIn("nothing was compared", err)

    def test_a_file_no_check_could_read_is_two(self):
        """Two columns of prose. Nothing was compared, so this is not clean."""
        code, _, err = call(str(temp("a.csv", "Notes,Comment\nhello,world\n")))
        self.assertEqual(code, 2)
        self.assertIn("nothing was compared", err)

    def test_an_unknown_check_name_is_two(self):
        code, _, err = call(str(temp("a.csv", CLEAN)), "--skip", "wibble")
        self.assertEqual(code, 2)
        self.assertIn("no check is called", err)


class Output(unittest.TestCase):
    def test_the_report_names_the_checks_that_did_not_run(self):
        _, out, _ = call(str(temp("a.csv", CLEAN)))
        self.assertIn("DID NOT RUN", out)
        self.assertIn("has found nothing because it was not made", out)

    def test_a_clean_run_does_not_claim_more_than_it_checked(self):
        _, out, _ = call(str(temp("a.csv", CLEAN)))
        self.assertIn("about the checks that ran", out)

    def test_json_is_valid_and_carries_the_checks_that_did_not_run(self):
        _, out, _ = call(str(temp("a.csv", DIRTY)), "--format", "json")
        payload = json.loads(out)
        checks = payload["tables"][0]["checks"]
        self.assertEqual(len(checks), len(CHECK_NAMES))
        self.assertTrue(any(not c["ran"] for c in checks))
        self.assertTrue(any(c["findings"] for c in checks))

    def test_markdown_has_the_ran_table(self):
        _, out, _ = call(str(temp("a.csv", DIRTY)), "--format", "markdown")
        self.assertIn("| check | ran | findings | why |", out)

    def test_skipping_says_it_was_skipped_rather_than_silently_passing(self):
        _, out, _ = call(str(temp("a.csv", DIRTY)), "--skip", "volume-tier")
        self.assertIn("switched off with --skip", out)


class Listings(unittest.TestCase):
    def test_list_checks_prints_all_seven(self):
        code, out, _ = call("--list-checks")
        self.assertEqual(code, 0)
        for name in CHECK_NAMES:
            self.assertIn(name, out)

    def test_list_columns_prints_the_vocabulary(self):
        code, out, _ = call("--list-columns")
        self.assertEqual(code, 0)
        self.assertIn("unit_price", out)
        self.assertIn("qualifier", out)

    def test_no_path_at_all_is_two(self):
        code, _, err = call()
        self.assertEqual(code, 2)


class Mapping(unittest.TestCase):
    TEXT = "Widget ref,How many,Each\nA,1,10.00\nA,10,11.00\n"

    def test_without_a_map_the_unknown_columns_stop_the_check(self):
        code, out, _ = call(str(temp("a.csv", self.TEXT)))
        self.assertEqual(code, 2)

    def test_a_map_by_position_makes_the_check_run(self):
        code, out, _ = call(
            str(temp("a.csv", self.TEXT)),
            "--map", "1=item", "--map", "2=quantity", "--map", "3=unit_price",
        )
        self.assertEqual(code, 1)
        self.assertIn("volume-tier", out)

    def test_a_map_by_name_works_too(self):
        code, _, _ = call(
            str(temp("a.csv", self.TEXT)),
            "--map", "Widget ref=item", "--map", "How many=quantity",
            "--map", "Each=unit_price",
        )
        self.assertEqual(code, 1)

    def test_an_unknown_role_is_refused_with_the_list(self):
        code, _, err = call(str(temp("a.csv", self.TEXT)), "--map", "1=wibble")
        self.assertEqual(code, 2)
        self.assertIn("is not a role", err)

    def test_an_unknown_column_name_is_refused_with_the_columns(self):
        code, _, err = call(str(temp("a.csv", self.TEXT)), "--map", "Nope=item")
        self.assertEqual(code, 2)
        self.assertIn("no column is called", err)

    def test_a_malformed_map_is_refused(self):
        code, _, err = call(str(temp("a.csv", self.TEXT)), "--map", "justthis")
        self.assertEqual(code, 2)
        self.assertIn("COLUMN=ROLE", err)


class Examples(unittest.TestCase):
    """The files the README and CI both point at."""

    ROOT = Path(__file__).resolve().parent.parent / "examples"

    def test_the_examples_behave_as_documented(self):
        for name, expected in (
            ("volume-tiers.csv", 1),
            ("discount-schedule.csv", 1),
            ("rate-card.xlsx", 1),
            ("consistent.csv", 0),
        ):
            with self.subTest(name=name):
                path = self.ROOT / name
                self.assertTrue(path.exists(), f"{name} is missing")
                code, _, _ = call(str(path))
                self.assertEqual(code, expected)


if __name__ == "__main__":
    unittest.main()
