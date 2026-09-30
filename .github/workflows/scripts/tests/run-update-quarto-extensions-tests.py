#!/usr/bin/env python3
"""Assert load-bearing contracts and unit tests for update-quarto-extensions.

Usage:
    python3 run-update-quarto-extensions-tests.py
    python3 run-update-quarto-extensions-tests.py --self-test
"""

from __future__ import annotations

import argparse
import io
import json
import os
import pathlib
import shutil
import sys
import tarfile
import tempfile
import unittest

try:
    import yaml
except ImportError:
    print(
        "::error::PyYAML is required to run update-quarto-extensions workflow tests.",
        file=sys.stderr,
    )
    sys.exit(1)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
SCRIPTS_DIR = REPO_ROOT / ".github" / "workflows" / "scripts"
import importlib.util

spec = importlib.util.spec_from_file_location(
    "update_quarto_extensions", SCRIPTS_DIR / "update-quarto-extensions.py"
)
uqe = importlib.util.module_from_spec(spec)
sys.modules["update_quarto_extensions"] = uqe
spec.loader.exec_module(uqe)

DEFAULT_WORKFLOW = (
    REPO_ROOT / ".github" / "workflows" / "update-quarto-extensions.yml"
)
DEFAULT_ACTION = (
    REPO_ROOT / ".github" / "actions" / "update-quarto-extensions" / "action.yml"
)
DEFAULT_EXAMPLE = REPO_ROOT / "examples" / "update-quarto-extensions.yml"
DEFAULT_REFERENCE = (
    REPO_ROOT / "website" / "reference" / "update-quarto-extensions.qmd"
)
QUARTO_YML = REPO_ROOT / "website" / "_quarto.yml"

EXPECTED_WORKFLOW_INPUTS = {
    "extension-repos": "string",
    "extensions-dir": "string",
    "base-branch": "string",
    "pr-branch": "string",
    "labels": "string",
    "dry-run": "boolean",
    "allow-local-edits": "boolean",
}


def load_yaml(path: pathlib.Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


class TestUpdateQuartoExtensionsContract(unittest.TestCase):
    """Assert workflow, action, example, and reference document contracts."""

    def test_workflow_file_exists_and_is_workflow_call(self):
        self.assertTrue(
            DEFAULT_WORKFLOW.is_file(),
            f"Missing workflow file: {DEFAULT_WORKFLOW}",
        )
        data = load_yaml(DEFAULT_WORKFLOW)
        on_data = data.get("on") or data.get(True) or {}
        self.assertIn("workflow_call", on_data)

    def test_workflow_inputs_and_types(self):
        data = load_yaml(DEFAULT_WORKFLOW)
        on_data = data.get("on") or data.get(True) or {}
        inputs = on_data.get("workflow_call", {}).get("inputs", {})
        for name, expected_type in EXPECTED_WORKFLOW_INPUTS.items():
            self.assertIn(name, inputs, f"Workflow missing input: {name}")
            self.assertEqual(
                inputs[name].get("type"),
                expected_type,
                f"Input '{name}' has type '{inputs[name].get('type')}', expected '{expected_type}'",
            )

    def test_workflow_permissions(self):
        data = load_yaml(DEFAULT_WORKFLOW)
        job = data.get("jobs", {}).get("update", {})
        perms = job.get("permissions", {})
        self.assertEqual(perms.get("contents"), "write")
        self.assertEqual(perms.get("pull-requests"), "write")

    def test_composite_action_exists(self):
        self.assertTrue(
            DEFAULT_ACTION.is_file(),
            f"Missing composite action: {DEFAULT_ACTION}",
        )
        data = load_yaml(DEFAULT_ACTION)
        self.assertEqual(data.get("runs", {}).get("using"), "composite")

    def test_example_file_pins_v3(self):
        self.assertTrue(
            DEFAULT_EXAMPLE.is_file(),
            f"Missing example file: {DEFAULT_EXAMPLE}",
        )
        content = DEFAULT_EXAMPLE.read_text(encoding="utf-8")
        self.assertIn(
            "uses: Morrison-Lab/gha/.github/workflows/update-quarto-extensions.yml@v3",
            content,
        )

    def test_reference_doc_registered_in_quarto_yml(self):
        self.assertTrue(
            DEFAULT_REFERENCE.is_file(),
            f"Missing reference doc: {DEFAULT_REFERENCE}",
        )
        quarto_content = QUARTO_YML.read_text(encoding="utf-8")
        self.assertIn("reference/update-quarto-extensions.qmd", quarto_content)

    def test_reference_doc_documents_inputs(self):
        ref_content = DEFAULT_REFERENCE.read_text(encoding="utf-8")
        for input_name in EXPECTED_WORKFLOW_INPUTS:
            self.assertIn(f"`{input_name}`", ref_content)


class TestUpdateQuartoExtensionsLogic(unittest.TestCase):
    """Unit tests for the updater logic, layout preservation, and safety checks."""

    def test_semver_parsing(self):
        self.assertEqual(
            uqe.parse_semver("1.0.0"), (1, 0, 0, 1, "")
        )
        self.assertEqual(
            uqe.parse_semver("v1.2.3"), (1, 2, 3, 1, "")
        )
        self.assertEqual(
            uqe.parse_semver("2.0.0-beta.1"), (2, 0, 0, 0, "beta.1")
        )
        self.assertIsNone(uqe.parse_semver("invalid-version"))

        # Sorting: 1.0.0 < 1.0.1 < 1.0.2
        v1 = uqe.parse_semver("1.0.0")
        v2 = uqe.parse_semver("v1.0.2")
        v3 = uqe.parse_semver("v1.0.2-rc1")
        self.assertLess(v1, v2)
        self.assertLess(v3, v2)

    def test_repo_map_parsing(self):
        # JSON
        json_map = '{"code-language-labels": "d-morrison/code-language-labels", "foo": "bar/baz"}'
        parsed = uqe.parse_repo_map(json_map)
        self.assertEqual(parsed.get("code-language-labels"), "d-morrison/code-language-labels")
        self.assertEqual(parsed.get("foo"), "bar/baz")

        # Key-value lines
        kv_map = """
        # Comment line
        code-language-labels: d-morrison/code-language-labels
        div-anchors: d-morrison/div-anchors
        other = org/other
        """
        parsed_kv = uqe.parse_repo_map(kv_map)
        self.assertEqual(parsed_kv.get("code-language-labels"), "d-morrison/code-language-labels")
        self.assertEqual(parsed_kv.get("div-anchors"), "d-morrison/div-anchors")
        self.assertEqual(parsed_kv.get("other"), "org/other")

        # Default extension repos
        self.assertEqual(
            uqe.DEFAULT_EXTENSION_REPOS.get("slidebreak"),
            "Morrison-Lab/slidebreak",
        )
        self.assertIn("code-language-labels", uqe.DEFAULT_EXTENSION_REPOS)
        self.assertIn("div-anchors", uqe.DEFAULT_EXTENSION_REPOS)
        self.assertIn("equation-anchors", uqe.DEFAULT_EXTENSION_REPOS)
        self.assertIn("revealjs-html-links", uqe.DEFAULT_EXTENSION_REPOS)
        self.assertNotIn("callouty-theorem", uqe.DEFAULT_EXTENSION_REPOS)

    def test_discovery_flat_and_nested_layouts(self):
        with tempfile.TemporaryDirectory() as tmp_dir_str:
            tmp_dir = pathlib.Path(tmp_dir_str)
            exts_dir = tmp_dir / "_extensions"

            # Create flat layout: _extensions/code-language-labels/_extension.yml
            flat_dir = exts_dir / "code-language-labels"
            flat_dir.mkdir(parents=True)
            (flat_dir / "_extension.yml").write_text(
                "title: Code Language Labels\nversion: 1.0.0\n", encoding="utf-8"
            )

            # Create nested layout: _extensions/d-morrison/div-anchors/_extension.yml
            nested_dir = exts_dir / "d-morrison" / "div-anchors"
            nested_dir.mkdir(parents=True)
            (nested_dir / "_extension.yml").write_text(
                "title: Div Anchors\nversion: 0.2.1\n", encoding="utf-8"
            )

            discovered = uqe.find_vendored_extensions(exts_dir)
            self.assertEqual(len(discovered), 2)

            rel_paths = {d["rel_path"] for d in discovered}
            self.assertIn("code-language-labels", rel_paths)
            self.assertIn("d-morrison/div-anchors", rel_paths)

    def test_directory_matching_handles_line_endings(self):
        with tempfile.TemporaryDirectory() as tmp_dir_str:
            tmp_dir = pathlib.Path(tmp_dir_str)
            dir_a = tmp_dir / "a"
            dir_b = tmp_dir / "b"
            dir_a.mkdir()
            dir_b.mkdir()

            # Same text, different CRLF vs LF
            (dir_a / "test.txt").write_bytes(b"hello\r\nworld\r\n")
            (dir_b / "test.txt").write_bytes(b"hello\nworld\n")

            self.assertTrue(uqe.directories_match(dir_a, dir_b))

            # Modify content
            (dir_b / "test.txt").write_bytes(b"hello\nmodified\n")
            self.assertFalse(uqe.directories_match(dir_a, dir_b))

    def _create_mock_tarball(
        self,
        tarball_path: pathlib.Path,
        ext_name: str,
        version: str,
        files: dict[str, str],
        nested_in_archive: bool = True,
        title: str = "",
    ) -> None:
        """Create a mock GitHub release tarball."""
        with tempfile.TemporaryDirectory() as src_dir_str:
            src_root = pathlib.Path(src_dir_str) / f"repo-{version}"
            if nested_in_archive:
                target_ext_dir = src_root / "_extensions" / ext_name
            else:
                target_ext_dir = src_root
            target_ext_dir.mkdir(parents=True)

            t_str = title or ext_name.replace("-", " ").title()
            manifest_content = f"title: {t_str}\nversion: {version}\n"
            (target_ext_dir / "_extension.yml").write_text(
                manifest_content, encoding="utf-8"
            )
            for fname, fcontent in files.items():
                (target_ext_dir / fname).write_text(fcontent, encoding="utf-8")

            with tarfile.open(tarball_path, "w:gz") as tar:
                tar.add(src_root, arcname=src_root.name)

    def test_in_place_update_preserves_flat_and_nested_layout(self):
        with tempfile.TemporaryDirectory() as tmp_dir_str:
            tmp_dir = pathlib.Path(tmp_dir_str)
            exts_dir = tmp_dir / "_extensions"

            # Create flat layout: _extensions/code-language-labels
            flat_dir = exts_dir / "code-language-labels"
            flat_dir.mkdir(parents=True)
            (flat_dir / "_extension.yml").write_text(
                "title: Code Language Labels\nversion: 1.0.0\n", encoding="utf-8"
            )
            (flat_dir / "code.lua").write_text("v1.0.0 code", encoding="utf-8")

            # Create nested layout: _extensions/d-morrison/div-anchors
            nested_dir = exts_dir / "d-morrison" / "div-anchors"
            nested_dir.mkdir(parents=True)
            (nested_dir / "_extension.yml").write_text(
                "title: Div Anchors\nversion: 0.1.0\n", encoding="utf-8"
            )
            (nested_dir / "div.lua").write_text("v0.1.0 div", encoding="utf-8")

            # Also create _quarto.yml outside _extensions to assert it is never touched
            quarto_yml = tmp_dir / "_quarto.yml"
            quarto_yml.write_text("project:\n  type: website\n", encoding="utf-8")

            # Mock download and API
            def mock_fetch_api(endpoint, token=None):
                if "code-language-labels" in endpoint:
                    return [{"name": "v1.0.2"}, {"name": "v1.0.0"}]
                if "div-anchors" in endpoint:
                    return [{"name": "v0.2.0"}, {"name": "v0.1.0"}]
                return []

            def mock_download_tarball(repo, ref, dest, token=None):
                if "code-language-labels" in repo:
                    ver = ref.lstrip("v")
                    self._create_mock_tarball(
                        dest,
                        "code-language-labels",
                        ver,
                        {"code.lua": f"v{ver} code"},
                        title="Code Language Labels",
                    )
                elif "div-anchors" in repo:
                    ver = ref.lstrip("v")
                    self._create_mock_tarball(
                        dest,
                        "div-anchors",
                        ver,
                        {"div.lua": f"v{ver} div"},
                        title="Div Anchors",
                    )

            orig_fetch = uqe.fetch_github_api
            orig_download = uqe.download_github_tarball
            uqe.fetch_github_api = mock_fetch_api
            uqe.download_github_tarball = mock_download_tarball

            try:
                updates = uqe.update_extensions(
                    extensions_dir=exts_dir,
                    repo_map=uqe.DEFAULT_EXTENSION_REPOS,
                )
            finally:
                uqe.fetch_github_api = orig_fetch
                uqe.download_github_tarball = orig_download

            self.assertEqual(len(updates), 2)

            # Assert flat layout remained flat (no nested directory created)
            self.assertTrue((flat_dir / "_extension.yml").is_file())
            self.assertEqual(
                (flat_dir / "code.lua").read_text(encoding="utf-8"),
                "v1.0.2 code",
            )
            self.assertFalse((flat_dir / "code-language-labels").exists())

            # Assert nested layout remained nested
            self.assertTrue((nested_dir / "_extension.yml").is_file())
            self.assertEqual(
                (nested_dir / "div.lua").read_text(encoding="utf-8"),
                "v0.2.0 div",
            )

            # Assert _quarto.yml was never modified
            self.assertEqual(
                quarto_yml.read_text(encoding="utf-8"),
                "project:\n  type: website\n",
            )

    def test_local_edits_detected_and_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp_dir_str:
            tmp_dir = pathlib.Path(tmp_dir_str)
            exts_dir = tmp_dir / "_extensions"

            flat_dir = exts_dir / "code-language-labels"
            flat_dir.mkdir(parents=True)
            (flat_dir / "_extension.yml").write_text(
                "title: Code Language Labels\nversion: 1.0.0\n", encoding="utf-8"
            )
            # Locally edited file that does not match the upstream tag
            (flat_dir / "code.lua").write_text("uncommitted local edit", encoding="utf-8")

            def mock_fetch_api(endpoint, token=None):
                return [{"name": "v1.0.2"}, {"name": "v1.0.0"}]

            def mock_download_tarball(repo, ref, dest, token=None):
                ver = ref.lstrip("v")
                self._create_mock_tarball(
                    dest,
                    "code-language-labels",
                    ver,
                    {"code.lua": f"clean upstream {ver}"},
                )

            orig_fetch = uqe.fetch_github_api
            orig_download = uqe.download_github_tarball
            uqe.fetch_github_api = mock_fetch_api
            uqe.download_github_tarball = mock_download_tarball

            try:
                # Should fail loudly because local edits were detected
                with self.assertRaises(RuntimeError) as ctx:
                    uqe.update_extensions(
                        extensions_dir=exts_dir,
                        repo_map=uqe.DEFAULT_EXTENSION_REPOS,
                        allow_local_edits=False,
                    )
                self.assertIn("local edits", str(ctx.exception).lower())

                # With allow_local_edits=True, should succeed
                updates = uqe.update_extensions(
                    extensions_dir=exts_dir,
                    repo_map=uqe.DEFAULT_EXTENSION_REPOS,
                    allow_local_edits=True,
                )
                self.assertEqual(len(updates), 1)
            finally:
                uqe.fetch_github_api = orig_fetch
                uqe.download_github_tarball = orig_download

    def test_dry_run_makes_no_changes(self):
        with tempfile.TemporaryDirectory() as tmp_dir_str:
            tmp_dir = pathlib.Path(tmp_dir_str)
            exts_dir = tmp_dir / "_extensions"

            flat_dir = exts_dir / "code-language-labels"
            flat_dir.mkdir(parents=True)
            (flat_dir / "_extension.yml").write_text(
                "title: Code Language Labels\nversion: 1.0.0\n", encoding="utf-8"
            )
            (flat_dir / "code.lua").write_text("clean upstream 1.0.0", encoding="utf-8")

            def mock_fetch_api(endpoint, token=None):
                return [{"name": "v1.0.2"}, {"name": "v1.0.0"}]

            def mock_download_tarball(repo, ref, dest, token=None):
                ver = ref.lstrip("v")
                self._create_mock_tarball(
                    dest,
                    "code-language-labels",
                    ver,
                    {"code.lua": f"clean upstream {ver}"},
                    title="Code Language Labels",
                )

            orig_fetch = uqe.fetch_github_api
            orig_download = uqe.download_github_tarball
            uqe.fetch_github_api = mock_fetch_api
            uqe.download_github_tarball = mock_download_tarball

            try:
                updates = uqe.update_extensions(
                    extensions_dir=exts_dir,
                    repo_map=uqe.DEFAULT_EXTENSION_REPOS,
                    dry_run=True,
                )
            finally:
                uqe.fetch_github_api = orig_fetch
                uqe.download_github_tarball = orig_download

            self.assertEqual(len(updates), 1)
            # File on disk must remain at 1.0.0
            self.assertEqual(
                (flat_dir / "code.lua").read_text(encoding="utf-8"),
                "clean upstream 1.0.0",
            )

    def test_pr_title_and_body_formatting(self):
        # Single update
        single = [
            {
                "name": "code-language-labels",
                "path": "code-language-labels",
                "old_version": "1.0.0",
                "new_version": "1.0.2",
                "repo": "d-morrison/code-language-labels",
                "tag": "v1.0.2",
            }
        ]
        title, body = uqe.format_pr_title_and_body(single)
        self.assertEqual(
            title, "chore: update Quarto extension code-language-labels to 1.0.2"
        )
        self.assertIn("`code-language-labels`", body)
        self.assertIn("1.0.0", body)
        self.assertIn("1.0.2", body)

        # Multiple updates
        multi = single + [
            {
                "name": "div-anchors",
                "path": "d-morrison/div-anchors",
                "old_version": "0.1.0",
                "new_version": "0.2.0",
                "repo": "d-morrison/div-anchors",
                "tag": "v0.2.0",
            }
        ]
        multi_title, multi_body = uqe.format_pr_title_and_body(multi)
        self.assertEqual(multi_title, "chore: update Quarto extensions")
        self.assertIn("`div-anchors`", multi_body)


def main():
    parser = argparse.ArgumentParser(
        description="Run update-quarto-extensions tests."
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run self-tests and exit with 0 on pass.",
    )
    args = parser.parse_args()

    suite = unittest.TestLoader().loadTestsFromTestCase(
        TestUpdateQuartoExtensionsContract
    )
    suite.addTests(
        unittest.TestLoader().loadTestsFromTestCase(
            TestUpdateQuartoExtensionsLogic
        )
    )

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        sys.exit(1)


if __name__ == "__main__":
    main()
