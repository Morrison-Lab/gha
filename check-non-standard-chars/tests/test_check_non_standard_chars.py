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

    def test_cp1252_console_does_not_crash(self):
        import subprocess
        res = subprocess.run(
            [sys.executable, str(script_path)],
            env=dict(os.environ, PYTHONIOENCODING="cp1252"),
            capture_output=True,
            text=False,
        )
        self.assertEqual(res.returncode, 0, f"script exited {res.returncode}: {res.stderr.decode('utf-8', errors='replace')}")

    def test_find_files_ignores_untracked_files_in_git_checkout(self):
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / "tracked.md").write_text("plain\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "tracked.md"], check=True)
            (root / "leftover").mkdir()
            (root / "leftover" / "untracked.md").write_text("a — b\n", encoding="utf-8")
            found = cnsc.find_files(root, [".md"])
            self.assertEqual([f.name for f in found], ["tracked.md"])

    def test_find_files_falls_back_to_glob_outside_git(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "a.md").write_text("x\n", encoding="utf-8")
            found = cnsc.find_files(root, [".md"])
            self.assertEqual([f.name for f in found], ["a.md"])


if __name__ == "__main__":
    unittest.main()
