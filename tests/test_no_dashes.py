"""No punctuation dash may reach a reader, in any format.

A dash is banned as punctuation in everything published under this author's
name, and a program's output is published under his name every time it runs.
The rule is about punctuation only: a hyphen inside a compound word, inside a
proper name, and inside an identifier such as ``volume-tier`` or ``adds-up``
is spelling, and is left alone.

Three things are deliberately not dashes and are excluded here, because they
are syntax a reader never sees as punctuation:

* a markdown bullet, which is a hyphen at the start of a line,
* a markdown table's ``|---|`` separator row,
* a rule line of repeated hyphens.

The test drives every renderer and every ``--format`` the README documents,
over an input built to reach the branches that used to carry a dash: a check
that did not run (the markdown table's placeholder cell), a column with no
role, and a check that ran without comparing anything.
"""

import contextlib
import io
import re
import tempfile
import unittest
from pathlib import Path

from adds_up import report
from adds_up.analyse import analyse
from adds_up.cli import build_parser, main
from adds_up.columns import vocabulary_lines

#: Every dash that is punctuation rather than spelling. ``-`` is absent on
#: purpose: it is legitimate inside a compound word and inside a name.
DASHES = {
    "‐": "HYPHEN",
    "‑": "NON-BREAKING HYPHEN",
    "‒": "FIGURE DASH",
    "–": "EN DASH",
    "—": "EM DASH",
    "―": "HORIZONTAL BAR",
    "−": "MINUS SIGN",
    "⸺": "TWO-EM DASH",
    "⸻": "THREE-EM DASH",
    "﹘": "SMALL EM DASH",
    "﹣": "SMALL HYPHEN-MINUS",
    "－": "FULLWIDTH HYPHEN-MINUS",
}

_BULLET = re.compile(r"^\s*[-*+]\s")
_TABLE_SEPARATOR = re.compile(r"^\s*\|[\s\-:|]+\|\s*$")
_RULE_LINE = re.compile(r"^\s*-{3,}\s*$")

#: A discount percentage, a list price, a bundle's components and a range's
#: ends are all absent, so four checks cannot run and the markdown table must
#: render four placeholder cells. ``Random blob`` is a column no role fits.
SAMPLE = (
    "SKU,Quantity,Unit price,Random blob\n"
    "W-1,50,11.20,zz\n"
    "W-1,250,11.80,yy\n"
)


def _offending(text: str) -> list[str]:
    """Every punctuation dash in ``text``, with the line it sits on."""
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        body = line
        if _TABLE_SEPARATOR.match(line) or _RULE_LINE.match(line):
            continue
        if _BULLET.match(line):
            body = _BULLET.sub("", line, count=1)
        for character, name in DASHES.items():
            if character in body:
                found.append(f"line {number}: {name} in {line.strip()!r}")
        if " -- " in body:
            found.append(f"line {number}: SPACED DOUBLE HYPHEN in {line.strip()!r}")
        if " - " in body:
            found.append(f"line {number}: SPACED HYPHEN in {line.strip()!r}")
    return found


def _call(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


def _sample_file() -> Path:
    path = Path(tempfile.mkdtemp()) / "sample.csv"
    path.write_text(SAMPLE, encoding="utf-8")
    return path


class NoDashReachesTheReader(unittest.TestCase):
    def assertNoDash(self, text: str, what: str):
        offending = _offending(text)
        self.assertEqual(
            offending, [], f"{what} contains a punctuation dash:\n" + "\n".join(offending)
        )

    # ---- the three renderers, called directly ----

    def test_text_renderer(self):
        result = analyse(_sample_file())
        self.assertNoDash(report.text(result, "0.0.0"), "the text report")

    def test_markdown_renderer(self):
        result = analyse(_sample_file())
        self.assertNoDash(report.markdown(result, "0.0.0"), "the markdown report")

    def test_json_renderer(self):
        result = analyse(_sample_file())
        self.assertNoDash(report.as_json(result, "0.0.0"), "the json report")

    # ---- the markdown table, which is where a placeholder cell lives ----

    def test_markdown_table_placeholders_are_words_and_the_table_is_intact(self):
        result = analyse(_sample_file())
        rows = [
            line for line in report.markdown(result, "0.0.0").splitlines()
            if line.startswith("|")
        ]
        self.assertTrue(rows, "the markdown report printed no table")
        for row in rows:
            cells = [cell.strip() for cell in row.strip("|").split("|")]
            self.assertEqual(len(cells), 5, f"a table row lost a cell: {row!r}")
        body = [row for row in rows if not _TABLE_SEPARATOR.match(row)][1:]
        not_run = [row for row in body if "**no**" in row]
        self.assertTrue(not_run, "no check was left un-run, so nothing was proved")
        for row in not_run:
            cells = [cell.strip() for cell in row.strip("|").split("|")]
            # An empty cell would read as a zero, which is the one thing this
            # tool exists not to let a reader believe.
            self.assertEqual(cells[2], "not run", f"placeholder cell: {row!r}")
            self.assertEqual(cells[3], "not run", f"placeholder cell: {row!r}")

    # ---- the text report's own placeholder ----

    def test_text_report_names_a_column_with_no_role(self):
        result = analyse(_sample_file())
        text = report.text(result, "0.0.0")
        self.assertIn("no role", text)
        self.assertNoDash(text, "the text report with an unroled column")

    # ---- every documented --format, through the command line ----

    def test_every_documented_format(self):
        path = str(_sample_file())
        for fmt in ("text", "markdown", "json"):
            with self.subTest(fmt=fmt):
                _, out, err = _call(path, "--format", fmt)
                self.assertNoDash(out, f"--format {fmt} on stdout")
                self.assertNoDash(err, f"--format {fmt} on stderr")

    # ---- the listing modes ----

    def test_list_checks(self):
        _, out, err = _call("--list-checks")
        self.assertNoDash(out, "--list-checks")
        self.assertNoDash(err, "--list-checks stderr")

    def test_list_columns(self):
        _, out, err = _call("--list-columns")
        self.assertNoDash(out, "--list-columns")
        self.assertNoDash(err, "--list-columns stderr")

    def test_vocabulary_lines_directly(self):
        self.assertNoDash("\n".join(vocabulary_lines()), "vocabulary_lines()")

    # ---- help, usage and the epilogue ----

    def test_help(self):
        self.assertNoDash(build_parser().format_help(), "--help")

    def test_usage(self):
        self.assertNoDash(build_parser().format_usage(), "the usage line")

    # ---- every error path that prints ----

    def test_error_messages(self):
        cases = [
            ([], "no path given"),
            (["/nonexistent/nope.csv"], "a path that does not exist"),
            ([str(_sample_file()), "--skip", "not-a-check"], "an unknown check"),
            ([str(_sample_file()), "--map", "nonsense"], "a malformed --map"),
            ([str(_sample_file()), "--map", "1=not_a_role"], "an unknown role"),
            ([str(_sample_file()), "--map", "'No Such'=quantity"], "an unknown column"),
        ]
        for argv, what in cases:
            with self.subTest(what=what):
                _, out, err = _call(*argv)
                self.assertNoDash(out, f"{what} on stdout")
                self.assertNoDash(err, f"{what} on stderr")

    # ---- the null-result warning, which must survive intact ----

    def test_null_result_warning(self):
        path = Path(tempfile.mkdtemp()) / "nothing.csv"
        path.write_text(
            "SKU,Quantity,UOM,Tariff amount payable\nW-1,1,each,9.00\n"
            "W-1,1000,each,50.00\n",
            encoding="utf-8",
        )
        code, out, err = _call(str(path))
        self.assertEqual(code, 2)
        self.assertIn("no two numbers were compared, so this is not a clean result", err)
        self.assertIn("See the CHECKS block for what each one was looking for.", err)
        self.assertNoDash(out, "a null result on stdout")
        self.assertNoDash(err, "the null-result warning")

    # ---- the shipped examples, which the README documents ----

    def test_the_shipped_examples(self):
        examples = sorted((Path(__file__).parent.parent / "examples").glob("*.*"))
        examples = [p for p in examples if p.suffix in (".csv", ".xlsx")]
        self.assertTrue(examples, "no example files were found")
        for example in examples:
            for fmt in ("text", "markdown", "json"):
                with self.subTest(example=example.name, fmt=fmt):
                    _, out, err = _call(str(example), "--format", fmt)
                    self.assertNoDash(out, f"{example.name} --format {fmt}")
                    self.assertNoDash(err, f"{example.name} --format {fmt} stderr")


class TheGuardItself(unittest.TestCase):
    """The detector has to be able to fail, or it proves nothing."""

    def test_it_catches_each_dash(self):
        for character, name in DASHES.items():
            with self.subTest(name=name):
                self.assertTrue(_offending(f"a{character}b"), f"{name} slipped through")

    def test_it_catches_the_ascii_impostors(self):
        # These print identically to a dash and match no search for one.
        self.assertTrue(_offending("a -- b"))
        self.assertTrue(_offending("a - b"))

    def test_it_allows_spelling(self):
        self.assertEqual(_offending("adds-up reports a volume-tier finding"), [])
        self.assertEqual(_offending("read-only, non-technical, GST-net"), [])

    def test_it_allows_markdown_syntax(self):
        self.assertEqual(_offending("- a bullet"), [])
        self.assertEqual(_offending("    - an indented bullet"), [])
        self.assertEqual(_offending("|---|---|---|"), [])
        self.assertEqual(_offending("-" * 74), [])

    def test_a_bullet_does_not_hide_a_dash_after_it(self):
        self.assertTrue(_offending("- a bullet — with a dash in it"))


if __name__ == "__main__":
    unittest.main()
