#!/usr/bin/env python3
"""Unit tests for export-extra-secrets.py (gha#618)."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Load export-extra-secrets.py via path
SCRIPT_PATH = Path(__file__).resolve().parent.parent / "export-extra-secrets.py"
spec = importlib.util.spec_from_file_location("export_extra_secrets", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
sys.modules["export_extra_secrets"] = mod
spec.loader.exec_module(mod)


class TestExportExtraSecrets(unittest.TestCase):
    def test_parse_secret_names_empty(self) -> None:
        self.assertEqual(mod.parse_secret_names(""), [])
        self.assertEqual(mod.parse_secret_names("   "), [])

    def test_parse_secret_names_delimiters(self) -> None:
        self.assertEqual(
            mod.parse_secret_names("EPI202_TOKEN EPI204_TOKEN"),
            ["EPI202_TOKEN", "EPI204_TOKEN"],
        )
        self.assertEqual(
            mod.parse_secret_names("EPI202_TOKEN, EPI204_TOKEN"),
            ["EPI202_TOKEN", "EPI204_TOKEN"],
        )
        self.assertEqual(
            mod.parse_secret_names("EPI202_TOKEN\nEPI204_TOKEN"),
            ["EPI202_TOKEN", "EPI204_TOKEN"],
        )
        self.assertEqual(
            mod.parse_secret_names("  EPI202_TOKEN,  \n EPI204_TOKEN  OTHER_KEY "),
            ["EPI202_TOKEN", "EPI204_TOKEN", "OTHER_KEY"],
        )

    def test_export_valid_secrets(self) -> None:
        secrets_data = {
            "EPI202_TOKEN": "secret_val_1",
            "EPI204_TOKEN": "secret_val_2\nmultiline",
            "IGNORED_SECRET": "should_not_export",
        }
        with tempfile.NamedTemporaryFile("w+", delete=False) as env_f:
            env_path = env_f.name

        try:
            captured_out = io.StringIO()
            sys_stdout = sys.stdout
            try:
                sys.stdout = captured_out
                ret = mod.export_secrets(
                    "EPI202_TOKEN EPI204_TOKEN",
                    json.dumps(secrets_data),
                    github_env_path=env_path,
                )
            finally:
                sys.stdout = sys_stdout

            self.assertEqual(ret, 0)
            stdout = captured_out.getvalue()
            self.assertIn("::add-mask::secret_val_1", stdout)
            self.assertIn("::add-mask::secret_val_2\nmultiline", stdout)
            self.assertIn("Exported 2 extra secret(s) to environment: EPI202_TOKEN, EPI204_TOKEN", stdout)

            with open(env_path, encoding="utf-8") as f:
                content = f.read()
            self.assertIn("EPI202_TOKEN<<", content)
            self.assertIn("secret_val_1", content)
            self.assertIn("EPI204_TOKEN<<", content)
            self.assertIn("secret_val_2\nmultiline", content)
            self.assertNotIn("IGNORED_SECRET", content)
        finally:
            if os.path.exists(env_path):
                os.remove(env_path)

    def test_reject_invalid_name(self) -> None:
        captured_err = io.StringIO()
        sys_stderr = sys.stderr
        try:
            sys.stderr = captured_err
            ret = mod.export_secrets("valid_lower invalid-hyphen 123_bad", "{}")
        finally:
            sys.stderr = sys_stderr

        self.assertEqual(ret, 1)
        stderr = captured_err.getvalue()
        self.assertIn("::error::Invalid secret name(s)", stderr)
        self.assertIn("valid_lower", stderr)
        self.assertIn("invalid-hyphen", stderr)
        self.assertIn("123_bad", stderr)

    def test_reject_protected_name(self) -> None:
        captured_err = io.StringIO()
        sys_stderr = sys.stderr
        try:
            sys.stderr = captured_err
            ret = mod.export_secrets("EPI202_TOKEN GITHUB_TOKEN PATH", "{}")
        finally:
            sys.stderr = sys_stderr

        self.assertEqual(ret, 1)
        stderr = captured_err.getvalue()
        self.assertIn("::error::Cannot export protected environment variable(s)", stderr)
        self.assertIn("GITHUB_TOKEN", stderr)
        self.assertIn("PATH", stderr)

    def test_warn_missing_secret(self) -> None:
        captured_out = io.StringIO()
        sys_stdout = sys.stdout
        try:
            sys.stdout = captured_out
            ret = mod.export_secrets(
                "EPI202_TOKEN MISSING_SECRET",
                json.dumps({"EPI202_TOKEN": "val"}),
            )
        finally:
            sys.stdout = sys_stdout

        self.assertEqual(ret, 0)
        stdout = captured_out.getvalue()
        self.assertIn("::warning::Secret 'MISSING_SECRET' requested via extra-secret-names was not found", stdout)
        self.assertIn("Exported 1 extra secret(s) to environment: EPI202_TOKEN", stdout)


if __name__ == "__main__":
    unittest.main()
