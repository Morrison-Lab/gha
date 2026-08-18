#!/usr/bin/env python3
import importlib.util
import os
import sys
import unittest
from pathlib import Path

# Load check-non-standard-chars.py as a module
script_path = Path(__file__).parent.parent / "check-non-standard-chars.py"
spec = importlib.util.spec_from_file_location("check_non_standard_chars", script_path)
cnsc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cnsc)


class TestCheckNonStandardChars(unittest.TestCase):
    def test_parse_extensions(self):
        self.assertEqual(cnsc.parse_extensions(""), [".qmd", ".R", ".md"])
        self.assertEqual(cnsc.parse_extensions(".qmd, .R, .md"), [".qmd", ".R", ".md"])
        self.assertEqual(cnsc.parse_extensions("qmd R md"), [".qmd", ".R", ".md"])
        self.assertEqual(cnsc.parse_extensions("txt, .md"), [".txt", ".md"])

    def test_non_standard_chars_dict(self):
        self.assertIn("\u201C", cnsc.NON_STANDARD_CHARS)
        self.assertIn("\u201D", cnsc.NON_STANDARD_CHARS)
        self.assertIn("\u2018", cnsc.NON_STANDARD_CHARS)
        self.assertIn("\u2019", cnsc.NON_STANDARD_CHARS)
        self.assertIn("\u2013", cnsc.NON_STANDARD_CHARS)
        self.assertIn("\u2014", cnsc.NON_STANDARD_CHARS)
        self.assertIn("\u00d7", cnsc.NON_STANDARD_CHARS)


if __name__ == "__main__":
    unittest.main()
