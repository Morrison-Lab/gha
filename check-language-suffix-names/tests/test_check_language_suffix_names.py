"""Unit tests for check-language-suffix-names.

Covers what counts as a finding (a name ending in ``_py``, ``_r`` or ``_jl``
that a line in an R, Python or Julia chunk binds), what does not (uses,
element and attribute assignments, keyword arguments, strings, comments,
other engines, plain fences), the allow comment, the diff scoping, and the
defaults the script, the action and the reusable workflow must agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_language_suffix_names", _DIR / "check-language-suffix-names.py")
assert _spec is not None and _spec.loader is not None
cln = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cln)

SUFFIXES = cln.DEFAULT_SUFFIXES.split()


def chunk(*code: str, engine: str = "{python}") -> str:
    return "\n".join([f"```{engine}", *code, "```"])


def found(text: str):
    """``(line, name)`` of the findings in a Markdown document."""
    hits, _ = cln.scan_markdown(text.split("\n"), SUFFIXES)
    return [(h.line, h.name) for h in hits]


# -- what is flagged ---------------------------------------------------------

@pytest.mark.parametrize("code, name", [
    ("x_py = 1", "x_py"),
    ("x_py: int = 1", "x_py"),
    ("x_py += 1", "x_py"),
    ("a_py, b = f()", "a_py"),
    ("a, b_py = f()", "b_py"),
    ("(a, b_py) = f()", "b_py"),
    ("[a, *rest_py] = xs", "rest_py"),
    ("for row_py in rows:", "row_py"),
    ("for i, v_py in enumerate(xs):", "v_py"),
    ("def fit_py(x):", "fit_py"),
    ("async def fit_py(x):", "fit_py"),
    ("class Model_py:", "Model_py"),
    ("import numpy as np_py", "np_py"),
    ("with open(p) as f_py:", "f_py"),
    ("if (n_py := len(x)) > 0:", "n_py"),
    ("fit_r = 1", "fit_r"),
])
def test_python_bindings_are_flagged(code, name):
    assert found(chunk(code)) == [(2, name)]


@pytest.mark.parametrize("code, name", [
    ("fit_r <- lm(y ~ x)", "fit_r"),
    ("fit_r = lm(y ~ x)", "fit_r"),
    ("fit_r <<- lm(y ~ x)", "fit_r"),
    ("lm(y ~ x) -> fit_r", "fit_r"),
    ("df |> head() ->> top_r", "top_r"),
    ("for (i_r in 1:3) print(i_r)", "i_r"),
    ("f_r <- function(x) x", "f_r"),
    ("model.fit_r <- 1", "model.fit_r"),
])
def test_r_bindings_are_flagged(code, name):
    assert found(chunk(code, engine="{r}")) == [(2, name)]


@pytest.mark.parametrize("code, name", [
    ("x_jl = 1", "x_jl"),
    ("const x_jl = 1", "x_jl"),
    ("global x_jl = 1", "x_jl"),
    ("local x_jl = 1", "x_jl"),
    ("x_jl = [1, 2];", "x_jl"),
    ("for i_jl = 1:3", "i_jl"),
    ("for i_jl in 1:3", "i_jl"),
    ("function fit_jl(x)", "fit_jl"),
    ("fit_jl(x) = 2x", "fit_jl"),
    ("update_jl!(x) = x", "update_jl!"),
    ("struct Model_jl", "Model_jl"),
])
def test_julia_bindings_are_flagged(code, name):
    assert found(chunk(code, engine="{julia}")) == [(2, name)]


@pytest.mark.parametrize("engine", [
    "{r}", "{R}", "{python}", "{julia}", "{r label}", "{python, echo=false}",
])
def test_every_executable_engine_is_read(engine):
    assert found(chunk("x_py = 1", engine=engine)) == [(2, "x_py")]


def test_each_suffixed_name_on_a_line_is_reported_once():
    assert found(chunk("a_py, b_py = f()")) == [(2, "a_py"), (2, "b_py")]


# -- what is not flagged -----------------------------------------------------

@pytest.mark.parametrize("code", [
    "print(x_py)",
    "y = x_py + 1",
    "x_py[0] = 1",
    "obj.x_py = 1",
    "f(n_py=1)",
    "f(n_py = 1)",
    "x_py == 1",
    "x_py <= 1",
    "x_py >= 1",
    "x_py != 1",
    "# x_py = 1",
    "s = 'x_py = 1'",
    'print("x_py = 1")',
    "x = 1  # was x_py",
    "x_python = 1",
    "x_rate = 1",
    "x_jlx = 1",
    "_py = 1",
    "__py = 1",
    "x = y_py",
    "for x in xs_py:",
    "lambda x_py: x_py",
    "x = 1",
])
def test_unbound_or_unsuffixed_is_not_flagged(code):
    assert found(chunk(code)) == []


@pytest.mark.parametrize("code", [
    "x <- fit_r",
    "fit_r$coef <- 1",
    "names(fit_r) <- 'a'",
    "lm(y ~ x, data = df_r)",
    "x <= fit_r",
])
def test_r_uses_are_not_flagged(code):
    assert found(chunk(code, engine="{r}")) == []


@pytest.mark.parametrize("engine", [
    "r", "python", "{{r}}", "{rcpp}", "{bash}", "{sql}", "{ojs}", "",
])
def test_other_fences_are_not_read(engine):
    assert found(chunk("x_py = 1", engine=engine)) == []


def test_prose_is_not_read():
    assert found("x_py = 1 in prose.\n\nfit_r <- 2") == []


def test_fence_inside_an_html_comment_opens_nothing():
    text = "<!--\n" + chunk("x_py = 1") + "\n-->"
    assert found(text) == []


def test_a_longer_fence_holds_a_shorter_one():
    text = "\n".join(["````{python}", "```", "x_py = 1", "````"])
    assert found(text) == [(3, "x_py")]


def test_an_unclosed_chunk_is_still_read():
    assert found("```{python}\nx_py = 1") == [(2, "x_py")]


def test_a_custom_suffix_list():
    hits, _ = cln.scan_markdown(chunk("x_py = 1", "y_tf = 2").split("\n"), ["_tf"])
    assert [(h.line, h.name) for h in hits] == [(3, "y_tf")]


# -- the allow comment -------------------------------------------------------

def test_allow_comment_with_a_reason_on_the_line():
    code = "x_py = 1  # check-language-suffix-names: allow: matches the paper"
    assert found(chunk(code)) == []


def test_allow_comment_on_the_line_before():
    assert found(chunk("# check-language-suffix-names: allow: needs both",
                       "x_py = 1", "y_py = 2")) == [(4, "y_py")]


def test_allow_comment_needs_a_reason():
    assert found(chunk("x_py = 1  # check-language-suffix-names: allow")) == [(2, "x_py")]
    assert found(chunk("x_py = 1  # check-language-suffix-names: allow:")) == [(2, "x_py")]


# -- scripts -----------------------------------------------------------------

@pytest.mark.parametrize("rel, code", [
    ("a.py", "x_py = 1"),
    ("a.R", "x_py <- 1"),
    ("a.r", "x_py <- 1"),
    ("a.jl", "x_py = 1"),
])
def test_scripts_are_read_whole(rel, code):
    hits, examined = cln.scan_file(rel, [code], SUFFIXES)
    assert [h.line for h in hits] == [1] and examined == 1


# -- helpers -----------------------------------------------------------------

def test_strip_code_line_blanks_strings_and_cuts_comments():
    assert cln.strip_code_line('x = "a#b" # c') == 'x = "   " '
    assert cln.strip_code_line("y = 'it\\'s'") == "y = '     '"


def test_message_names_the_language():
    msg = cln.format_message(cln.Finding(1, "x_py", "_py"))
    assert "'x_py'" in msg and "Python" in msg and "same name" in msg


def test_split_words():
    assert cln.split_words(" _py, _r  _jl ") == ["_py", "_r", "_jl"]


# -- diff scoping ------------------------------------------------------------

def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t",
                    "-c", "user.email=t@example.com", *args],  # phi-allow
                   check=True, capture_output=True)


BASE = chunk("old_py = 1", "y = 2") + "\n"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "page.qmd").write_text(BASE)
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "base")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _run(base_ref="HEAD", whole_tree=False, ignores=()):
    compiled = cln.diffscope.compile_ignores(list(ignores))
    return cln.run_check(base_ref, ["*.qmd"], compiled, whole_tree)


def _lines(report):
    return [(rel, f.line) for rel, f in report.findings]


def test_existing_name_on_an_untouched_line_is_not_reported(repo):
    (repo / "page.qmd").write_text(BASE + "New text.\n")
    report = _run()
    assert report.findings == [] and not report.skipped


def test_added_binding_is_reported(repo):
    (repo / "page.qmd").write_text(BASE + chunk("new_py = 3") + "\n")
    assert _lines(_run()) == [("page.qmd", 6)]


def test_added_use_of_an_existing_name_is_not_reported(repo):
    (repo / "page.qmd").write_text(BASE + chunk("print(old_py)") + "\n")
    assert _run().findings == []


def test_moved_line_is_not_new(repo):
    (repo / "page.qmd").write_text(chunk("y = 2") + "\n\nText.\n\n"
                                   + chunk("old_py = 1") + "\n")
    assert _run().findings == []


def test_paths_ignore(repo):
    (repo / "page.qmd").write_text(BASE + chunk("new_py = 3") + "\n")
    assert _run(ignores=["page.qmd"]).findings == []


def test_whole_tree_reports_the_existing_name(repo):
    assert _lines(_run(whole_tree=True)) == [("page.qmd", 2)]


def test_no_base_ref_skips_instead_of_scanning(repo):
    assert _run(base_ref="").skipped


def test_unresolvable_base_ref_skips(repo):
    assert _run(base_ref="no-such-ref").skipped


# -- main() ------------------------------------------------------------------

def test_main_blocks_by_default(repo, monkeypatch, capsys):
    (repo / "page.qmd").write_text(BASE + chunk("new_py = 3") + "\n")
    monkeypatch.setenv("CLN_BASE_REF", "HEAD")
    monkeypatch.delenv("CLN_FAIL", raising=False)
    assert cln.main() == 1
    assert "::error file=page.qmd,line=6::" in capsys.readouterr().out


def test_main_warns_when_fail_is_false(repo, monkeypatch, capsys):
    (repo / "page.qmd").write_text(BASE + chunk("new_py = 3") + "\n")
    monkeypatch.setenv("CLN_BASE_REF", "HEAD")
    monkeypatch.setenv("CLN_FAIL", "false")
    assert cln.main() == 0
    assert "::warning file=page.qmd,line=6::" in capsys.readouterr().out


def test_main_reads_suffixes(repo, monkeypatch):
    (repo / "page.qmd").write_text(BASE + chunk("new_py = 3") + "\n")
    monkeypatch.setenv("CLN_BASE_REF", "HEAD")
    monkeypatch.setenv("CLN_SUFFIXES", "_tf, _torch")
    assert cln.main() == 0


def test_main_reports_what_it_examined(repo, monkeypatch, capsys):
    (repo / "page.qmd").write_text(BASE + "Text.\n")
    monkeypatch.setenv("CLN_BASE_REF", "HEAD")
    assert cln.main() == 0
    assert "Examined 1 line(s) across 1 file(s)" in capsys.readouterr().out


def test_main_skips_without_a_base(repo, monkeypatch, capsys):
    (repo / "page.qmd").write_text(BASE + chunk("new_py = 3") + "\n")
    monkeypatch.delenv("CLN_BASE_REF", raising=False)
    assert cln.main() == 0
    assert "Skipping" in capsys.readouterr().out


# -- defaults declared in three places ---------------------------------------

def _default(path: Path, name: str) -> str:
    """The ``default:`` of input ``name`` in an action or workflow file."""
    lines = path.read_text().split("\n")
    for number, line in enumerate(lines):
        if re.fullmatch(rf"\s+{re.escape(name)}:\s*", line):
            for follow in lines[number + 1:number + 12]:
                found_default = re.match(r"\s+default:\s*(.*)", follow)
                if found_default:
                    return found_default.group(1).strip().strip("'\"")
    raise AssertionError(f"no default for {name} in {path}")


_ROOT = _DIR.parent
_FILES = [_DIR / "action.yml",
          _ROOT / ".github" / "workflows" / "check-language-suffix-names.yml"]


@pytest.mark.parametrize("path", _FILES, ids=lambda p: p.name)
def test_defaults_agree_with_the_script(path):
    assert _default(path, "globs") == cln.DEFAULT_GLOBS
    assert _default(path, "suffixes") == cln.DEFAULT_SUFFIXES
    assert _default(path, "fail") == str(cln._DEFAULT_FAIL).lower()
