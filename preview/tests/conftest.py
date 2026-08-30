"""Shared fixtures for the preview changed-chapter tests.

Every fixture is generated at run time. A committed HTML fixture would be swept
into the `phi`, `bib` and `typos` jobs' own repo-wide scans -- see CLAUDE.md's
"Generate selftest fixtures at runtime; don't commit them".
"""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

GIT_ENV = {
    "GIT_AUTHOR_NAME": "gha selftest",
    "GIT_AUTHOR_EMAIL": "selftest@example.invalid",
    "GIT_COMMITTER_NAME": "gha selftest",
    "GIT_COMMITTER_EMAIL": "selftest@example.invalid",
}


def _load(name, filename):
    # The scripts import a sibling module, which the composite gets for free
    # (a script's own directory leads sys.path) and a file-path load does not.
    preview_dir = str(REPO_ROOT / "preview")
    if preview_dir not in sys.path:
        sys.path.insert(0, preview_dir)
    path = REPO_ROOT / "preview" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


read_outputs = _load("gha_read_github_output", "tests/read-github-output.py")


@pytest.fixture(scope="session")
def detector():
    return _load("gha_detect_changed_chapters", "detect-changed-chapters.py")


@pytest.fixture(scope="session")
def banner():
    return _load("gha_add_home_banner", "add-home-banner.py")


def git(repo, *args):
    """Run git in an isolated environment, so a developer's own config cannot
    change what these tests measure."""
    env = {
        **os.environ,
        **GIT_ENV,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
    }
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, env=env)


def write(root, relative, content):
    target = Path(root) / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        target.write_bytes(content)
    else:
        target.write_text(content, encoding="utf-8")
    return target


@pytest.fixture
def repo_factory(tmp_path):
    """Build a work repo whose `origin` is a bare repo, optionally holding a deployed branch.

    `published` maps deployed-branch paths to contents; pass None to leave the
    branch absent, which is the case that must read as a stated skip rather than
    as an empty result.
    """

    counter = {"n": 0}

    def build(published, branch="gh-pages"):
        counter["n"] += 1
        base = tmp_path / f"case{counter['n']}"
        bare = base / "origin.git"
        bare.mkdir(parents=True)
        git(bare, "init", "--bare", "-b", "main")

        if published is not None:
            seed = base / "seed"
            seed.mkdir()
            git(seed, "init", "-b", branch)
            for relative, content in published.items():
                write(seed, relative, content)
            git(seed, "add", "-A")
            git(seed, "commit", "-m", "deployed render")
            git(seed, "push", str(bare), f"{branch}:{branch}")

        work = base / "work"
        work.mkdir()
        git(work, "init", "-b", "main")
        # file:// rather than a plain path: git ignores --depth over the local
        # transport, and the fetch here is deliberately shallow.
        git(work, "remote", "add", "origin", f"file://{bare}")
        return work

    return build
