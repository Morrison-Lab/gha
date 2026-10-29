r"""Every diff-scoped check reads its diff through the shared engine.

Four checks once carried their own copy of `git diff -U0 ...` and `parse_diff`,
so the silent skip under `diff.mnemonicPrefix` (gha#1355) lived in each of them
(gha#1357). This test keeps the copies from coming back: a script that runs the
diff must take the argument list and the parser from `check-write-idiom`.
"""

import importlib.util
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_ENGINE = _ROOT / "check-write-idiom" / "check-write-idiom.py"

SHARED_USERS = [
    "check-restated-results",
    "check-definition-equations",
    "check-redundant-citations",
    "check-macro-expansions",
    "check-avoided-words",
    "check-proof-statements",
]


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


engine = _load(_ENGINE, "engine_under_test")


@pytest.mark.parametrize("name", SHARED_USERS)
def test_check_has_no_private_diff_command_or_hunk_parser(name):
    source = (_ROOT / name / f"{name}.py").read_text()
    assert '"diff", "-U0"' not in source
    assert "_HUNK_RE" not in source


@pytest.mark.parametrize("name", [
    "check-restated-results",
    "check-definition-equations",
    "check-redundant-citations",
    "check-macro-expansions",
])
def test_check_runs_the_engines_diff_arguments(name):
    source = (_ROOT / name / f"{name}.py").read_text()
    assert "engine.GIT_DIFF_ARGS" in source
    module = _load(_ROOT / name / f"{name}.py", name.replace("-", "_"))
    assert module.engine.GIT_DIFF_ARGS == engine.GIT_DIFF_ARGS


def test_engine_diff_arguments_fix_the_prefixes():
    args = engine.GIT_DIFF_ARGS
    assert "--src-prefix=a/" in args and "--dst-prefix=b/" in args
    assert "--no-ext-diff" in args and "--no-textconv" in args


def test_line_number_parsers_drop_blank_added_lines():
    diff = "+++ b/a.qmd\n@@ -0,0 +1,3 @@\n+one\n+\n+three\n"
    for name in ("check-restated-results", "check-definition-equations"):
        module = _load(_ROOT / name / f"{name}.py", name.replace("-", "_"))
        assert module.parse_diff(diff) == {"a.qmd": {1, 3}}


def test_unquoted_paths_reach_the_line_number_parsers():
    diff = '+++ "b/ch/q\\"u.qmd"\n@@ -0,0 +1 @@\n+one\n'
    module = _load(_ROOT / "check-restated-results" / "check-restated-results.py", "rr")
    assert module.parse_diff(diff) == {'ch/q"u.qmd': {1}}
