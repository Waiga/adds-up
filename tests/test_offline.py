"""The promise that nothing leaves the machine, enforced as a test.

adds-up reads price lists, which are commercial documents. Its central claim
is that they stay on the machine that runs it. A sentence in a README cannot
enforce that. This test reads the package's own source and fails if any module
gains the ability to open a connection or start a process.

It checks four things, because no one of them is enough on its own:

* imports, against an allowlist — a denylist has to imagine every door;
* the parts of ``os`` that start another program, by name wherever they
  appear, so an alias or a ``from`` import cannot walk past;
* the dynamic escape hatches — ``__import__``, ``eval``, ``exec``,
  ``importlib``, ``sys.modules`` — which would let any of the above in with no
  import statement to find;
* that everything importable in the package is readable Python source, since a
  compiled extension would be just as importable and contain nothing to parse.

Every detector below has a test proving it can fail. A guard nobody has seen
fail is not a guard.
"""

import ast
import tempfile
import unittest
from pathlib import Path

import adds_up

PACKAGE = Path(adds_up.__file__).parent

#: The only modules this package may import. Eleven, and ``os`` is not one of
#: them: nothing here writes a file, so the exception ``os`` usually needs is
#: not needed either.
ALLOWED_MODULES = frozenset(
    {
        "__future__", "argparse", "csv", "dataclasses", "decimal", "json",
        "pathlib", "re", "sys", "xml", "zipfile",
    }
)

FORBIDDEN_OS_CALLS = frozenset(
    {
        "execl", "execle", "execlp", "execv", "execve", "execvp", "execvpe",
        "fork", "forkpty", "popen", "posix_spawn", "posix_spawnp", "spawnl",
        "spawnle", "spawnlp", "spawnv", "spawnve", "spawnvp", "spawnvpe",
        "startfile", "system",
    }
)

#: Ways to reach a forbidden capability without naming it in an import.
#: ``compile`` and ``getattr`` are deliberately absent from the attribute set
#: below but present here as bare names: ``re.compile`` is how every pattern in
#: this package is built.
FORBIDDEN_NAMES = frozenset(
    {
        "__builtins__", "__import__", "builtins", "eval", "exec", "globals",
        "importlib", "locals", "modules", "vars",
    }
)

FORBIDDEN_ATTRIBUTES = FORBIDDEN_OS_CALLS | {
    "__builtins__", "__dict__", "__getattribute__", "__globals__",
    "__import__", "__subclasses__", "eval", "exec", "modules",
}


def modules() -> list[Path]:
    return sorted(PACKAGE.rglob("*.py"))


def offences(source: str, filename: str = "<source>") -> set[str]:
    """Everything in ``source`` that would break the offline promise."""
    tree = ast.parse(source, filename=filename)
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in ALLOWED_MODULES:
                    found.add(f"import {root}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if node.level == 0 and root not in ALLOWED_MODULES:
                found.add(f"from {root} import ...")
            for alias in node.names:
                if alias.name == "*":
                    found.add(f"from {node.module} import *")
                elif alias.name in FORBIDDEN_OS_CALLS or alias.name in FORBIDDEN_NAMES:
                    found.add(f"from {node.module} import {alias.name}")
        elif isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_ATTRIBUTES:
                found.add(f".{node.attr}")
        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_OS_CALLS or node.id in FORBIDDEN_NAMES:
                found.add(node.id)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in FORBIDDEN_OS_CALLS:
                found.add(f"literal {node.value!r}")
    return found


class NothingLeavesTheMachine(unittest.TestCase):
    def test_there_are_modules_to_check(self):
        self.assertGreater(len(modules()), 5)

    def test_the_whole_package_is_scanned(self):
        names = {path.name for path in modules()}
        for expected in ("cli.py", "checks.py", "tables.py", "numbers.py", "columns.py"):
            self.assertIn(expected, names)

    def test_the_package_contains_nothing_but_python_source(self):
        """Everything importable must be something this check can read.

        A compiled extension or a sourceless ``.pyc`` in the package would be
        just as importable and would contain no source to parse, so it would
        pass unexamined. Rather than trying to inspect a binary, refuse to
        have one.
        """
        strays = [
            path
            for path in PACKAGE.rglob("*")
            if path.is_file()
            and path.suffix != ".py"
            and "__pycache__" not in path.parts
        ]
        self.assertEqual(strays, [], f"non-source files: {[str(p) for p in strays]}")

    def test_no_module_can_reach_out(self):
        for module in modules():
            with self.subTest(module=str(module.relative_to(PACKAGE))):
                found = offences(module.read_text(encoding="utf-8"), str(module))
                self.assertEqual(found, set(), f"{module.name}: {sorted(found)}")


class TheGuardCanFail(unittest.TestCase):
    """Each detector, shown catching the thing it exists to catch."""

    def assert_caught(self, source: str, expected: str):
        self.assertIn(expected, offences(source))

    def test_catches_a_plain_import(self):
        self.assert_caught("import socket\n", "import socket")

    def test_catches_a_dotted_import(self):
        self.assert_caught("import urllib.request\n", "import urllib")

    def test_catches_a_from_import(self):
        self.assert_caught("from http import client\n", "from http import ...")

    def test_catches_a_star_import(self):
        self.assert_caught("from urllib import *\n", "from urllib import *")

    def test_catches_os_itself(self):
        # os is not on the allowlist for this package at all.
        self.assert_caught("import os\n", "import os")

    def test_catches_a_process_launch(self):
        self.assert_caught("import os\nos.popen('curl example.com')\n", ".popen")
        self.assert_caught("from os import system\n", "from os import system")
        self.assert_caught("import os as o\no.popen('x')\n", ".popen")

    def test_catches_the_spawn_family_completely(self):
        for call in ("spawnv", "spawnvpe", "posix_spawn", "forkpty", "execve"):
            with self.subTest(call=call):
                self.assert_caught(f"import os\nos.{call}()\n", f".{call}")

    def test_catches_the_name_hidden_in_a_string(self):
        self.assert_caught("x = 'popen'\n", "literal 'popen'")

    def test_catches_the_private_accelerators(self):
        for module in ("_socket", "_ssl", "_ctypes", "_posixsubprocess"):
            with self.subTest(module=module):
                self.assert_caught(f"import {module}\n", f"import {module}")

    def test_catches_the_polite_front_doors(self):
        self.assert_caught(
            "from concurrent.futures import ProcessPoolExecutor\n",
            "from concurrent import ...",
        )
        self.assert_caught(
            "from logging.handlers import HTTPHandler\n", "from logging import ..."
        )

    def test_catches_a_module_nobody_thought_to_ban(self):
        for module in ("runpy", "pty", "venv", "wsgiref", "ftplib", "smtplib"):
            with self.subTest(module=module):
                self.assert_caught(f"import {module}\n", f"import {module}")

    def test_catches_reaching_through_a_dunder(self):
        self.assert_caught("import x\nx.__dict__['system']('y')\n", ".__dict__")
        self.assert_caught("x.__getattribute__('popen')()\n", ".__getattribute__")

    def test_catches_the_module_table(self):
        self.assert_caught("import sys\nsys.modules['socket']\n", ".modules")
        self.assert_caught("from sys import modules\n", "from sys import modules")

    def test_catches_the_dynamic_import_hatches(self):
        self.assert_caught("x = __import__('socket')\n", "__import__")
        self.assert_caught("import importlib\n", "import importlib")
        self.assert_caught("eval('1')\n", "eval")
        self.assert_caught("exec('pass')\n", "exec")

    def test_allows_what_this_package_actually_uses(self):
        source = (
            "import csv\nimport re\nimport zipfile\n"
            "from xml.etree import ElementTree\n"
            "from decimal import Decimal\n"
            "re.compile('x')\n"
        )
        self.assertEqual(offences(source), set())

    def test_a_real_smuggled_module_is_caught(self):
        source = (
            "import _socket\n"
            "from logging.handlers import SocketHandler\n"
            "\n"
            "def send(payload):\n"
            "    connection = _socket.socket()\n"
            "    connection.connect(('example.invalid', 80))\n"
            "    connection.send(payload)\n"
        )
        found = offences(source)
        self.assertIn("import _socket", found)
        self.assertIn("from logging import ...", found)

    def test_scanner_reads_a_file_from_disk(self):
        with tempfile.TemporaryDirectory() as directory:
            sample = Path(directory) / "sample.py"
            sample.write_text("import socket\n", encoding="utf-8")
            self.assertIn("import socket", offences(sample.read_text(encoding="utf-8")))


class WhatThisDoesNotCover(unittest.TestCase):
    """The limits of this check, written down rather than left to be found.

    This is a static read of one package's source: a guard against drift, not
    a sandbox. It does not run the code, it cannot see what a dependency does,
    and a name assembled at runtime from pieces — ``"po" + "pen"`` — never
    appears in the source for it to find.

    The larger gap is the filesystem. Reading files is the whole job, so
    ``pathlib`` and ``open`` are allowed, and no static read can tell a local
    path from a network one: an SMB or NFS mount, a UNC path or a FUSE
    filesystem reaches the network with no socket call in this package's
    source. That is real, and it is written here and in ``docs/limitations.md``
    rather than left to be discovered.
    """

    def test_the_package_declares_no_dependencies(self):
        manifest = (PACKAGE.parent / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("dependencies = []", manifest)


if __name__ == "__main__":
    unittest.main()
