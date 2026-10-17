"""G1 purity gate: passes on the real package, fails on planted violations (AC-01)."""

import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import incident_commander
from incident_commander import dod

PKG = Path(incident_commander.__file__).resolve().parent


class TestPurity(unittest.TestCase):
    def scan_with(self, extra_source: str):
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "incident_commander"
            shutil.copytree(PKG, copy, ignore=shutil.ignore_patterns("__pycache__"))
            (copy / "planted.py").write_text(extra_source, encoding="utf-8")
            return dod.scan(copy)[1]

    def test_real_package_passes(self):
        scanned, violations = dod.scan(PKG)
        self.assertEqual(violations, [])
        self.assertGreaterEqual(scanned, 10)

    def test_cli_prints_pass_and_returns_zero(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = dod.main(["purity"])
        self.assertEqual(rc, 0)
        self.assertIn("G1 purity: PASS", buf.getvalue())

    def test_third_party_import_fails(self):
        v = self.scan_with("import requests\n")
        self.assertEqual([x.message for x in v], ["forbidden import: requests"])

    def test_unlisted_third_party_import_fails(self):
        v = self.scan_with("import yaml\n")
        self.assertEqual(len(v), 1)
        self.assertIn("outside stdlib", v[0].message)

    def test_direct_numpy_and_network_modules_fail(self):
        for mod in ("numpy", "socket", "urllib.request", "http.client"):
            with self.subTest(mod=mod):
                self.assertEqual(len(self.scan_with(f"import {mod}\n")), 1)

    def test_from_import_of_forbidden_module_fails(self):
        self.assertEqual(len(self.scan_with("from urllib import request\n")), 1)

    def test_importing_ic_plus_fails(self):
        for src in ("import ic_plus\n", "from ic_plus import guard\n", "x = ic_plus.thing\n"):
            with self.subTest(src=src):
                self.assertTrue(self.scan_with(src), src)

    def test_environment_access_fails(self):
        for src in (
            "import os\nx = os.environ['K']\n",
            "import os\nx = os.getenv('K')\n",
            "from os import environ\n",
            "from os import getenv\n",
        ):
            with self.subTest(src=src):
                self.assertTrue(self.scan_with(src), src)

    def test_stdlib_sklearn_and_relative_imports_pass(self):
        src = "import json\nfrom sklearn.feature_extraction.text import TfidfVectorizer\nfrom . import types\n"
        self.assertEqual(self.scan_with(src), [])

    def test_cli_fails_with_nonzero_exit_on_violation(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "bad.py").write_text("import requests\n", encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = dod.main(["purity", "--root", tmp])
        self.assertEqual(rc, 1)
        self.assertIn("G1 purity: FAIL", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
