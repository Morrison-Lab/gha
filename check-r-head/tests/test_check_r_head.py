"""Unit tests for check-r-head.

Covers what counts as a finding (a top-level R statement that prints the
value of ``head()`` in a data div or data subfile), what does not (assigned or
used results, other engines, chunks outside data divs, methods such as
``.head()``), the allow comment, the diff scoping, and the defaults the
script, the action and the reusable workflow must agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("check_r_head", _DIR / "check-r-head.py")
assert _spec is not None and _spec.loader is not None
crh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(crh)


def chunk(*code: str, engine: str = "{r}") -> str:
    return "\n".join([f"```{engine}", *code, "```"])


def found(text: str, data_file: bool = True):
    """Line numbers of the findings in a document given as one string."""
    hits, _ = crh.scan_file(text.split("\n"), data_file)
    return [h.line for h in hits]


# -- which statements print head() ------------------------------------------

@pytest.mark.parametrize("code", [
    "head(df)",
    "head(df, 3)",
    "head(df, n = 10)",
    "utils::head(df)",
    "df |> head()",
    "df |> head(3)",
    "df %>% head()",
    "df %>% head",
    "df |> dplyr::filter(x > 1) |> head()",
    "print(head(df))",
    "print(head(df), n = 3)",
    "df |> head() |> print()",
    "  head(df)  # first rows",
    "head( df )",
    "head(df);",
])
def test_printed_head_is_flagged(code):
    assert found(chunk(code)) == [2]


@pytest.mark.parametrize("code", [
    "top <- head(df)",
    "top = head(df)",
    "head(df) -> top",
    "df |> head() -> top",
    "top <<- head(df)",
    "nrow(head(df))",
    "df |> head() |> knitr::kable()",
    "head(df) |> summary()",
    "print(nrow(head(df)))",
    "head(df)[1, ]",
    "head(df)$x",
    "f(head = 3)",
    "head",                 # prints the function, not data
    "df.head()",
    "x$head()",
    "py$df$head()",
    "dplyr::slice_head(df, n = 3)",
    "slice_head(df, n = 3)",
    "x %in% head(y)",
    "# head(df)",
    "cat('head(df)')",
    "\"head(df)\"",
    "lapply(dfs, head)",
    "head(df) == 1",
])
def test_unprinted_or_unrelated_is_not_flagged(code):
    assert found(chunk(code)) == []


def test_statement_inside_braces_is_not_top_level():
    text = chunk("f <- function(df) {", "  head(df)", "}")
    assert found(text) == []


def test_loop_body_is_not_top_level():
    assert found(chunk("for (d in dfs) {", "  head(d)", "}")) == []


def test_multiline_pipeline_reports_the_head_line():
    text = chunk("df |>", "  dplyr::select(x) |>", "  head()")
    assert found(text) == [4]


def test_multiline_call_is_one_statement():
    text = chunk("head(", "  df,", "  n = 3", ")")
    assert found(text) == [2]


def test_multiline_assignment_passes():
    text = chunk("top <- df |>", "  head()")
    assert found(text) == []


def test_semicolons_split_statements():
    assert found(chunk("x <- 1; head(df)")) == [2]
    assert found(chunk("head(df) -> a; b <- 2")) == []


def test_statements_after_a_flagged_one_are_read_afresh():
    text = chunk("head(df)", "top <- head(df)", "df |> head()")
    assert found(text) == [2, 4]


def test_every_chunk_is_read():
    text = "\n".join([chunk("df"), "Text.", chunk("head(df)")])
    assert found(text) == [6]


# -- which chunks are read ----------------------------------------------------

@pytest.mark.parametrize("engine", [
    "{r}", "{r label}", "{r, echo=FALSE}", "{R}", "{r }"])
def test_r_chunk_info_strings(engine):
    assert found(chunk("head(df)", engine=engine)) == [2]


@pytest.mark.parametrize("engine", [
    "{python}", "{julia}", "r", "{{r}}", "{rcpp}", "{ojs}", ""])
def test_other_engines_are_skipped(engine):
    assert found(chunk("head(df)", engine=engine)) == []


def test_python_head_method_is_skipped():
    assert found(chunk("df.head()", engine="{python}")) == []


def test_chunk_shown_inside_a_longer_fence_is_skipped():
    text = "\n".join(["````markdown", "```{r}", "head(df)", "```", "````"])
    assert found(text) == []


def test_tilde_fence_r_chunk_is_read():
    assert found("~~~{r}\nhead(df)\n~~~") == [2]


def test_chunk_in_an_html_comment_is_skipped():
    assert found("<!--\n" + chunk("head(df)") + "\n-->") == []


def test_unclosed_chunk_is_still_read():
    assert found("```{r}\nhead(df)") == [2]


# -- data divs and data subfiles ----------------------------------------------

def test_other_files_are_out_of_scope():
    assert found(chunk("head(df)"), data_file=False) == []


def test_chunk_in_a_dat_div_is_read():
    text = "\n".join(["::: {#dat-auto}", chunk("head(df)"), "", "Auto", ":::"])
    assert found(text, data_file=False) == [3]


def test_chunk_in_a_div_nested_in_a_dat_div_is_read():
    text = "\n".join(["::: {#dat-auto}", ":::: {.panel-tabset}",
                      chunk("head(df)"), "::::", ":::"])
    assert found(text, data_file=False) == [4]


def test_chunk_after_a_dat_div_closes_is_skipped():
    text = "\n".join(["::: {#dat-auto}", "Auto", ":::", chunk("head(df)")])
    assert found(text, data_file=False) == []


def test_chunk_in_another_div_is_skipped():
    text = "\n".join(["::: {#exm-auto}", chunk("head(df)"), ":::"])
    assert found(text, data_file=False) == []


def test_dat_id_must_be_an_id():
    text = "\n".join(["::: {.note data-x=#dat-y}", chunk("head(df)"), ":::"])
    assert found(text, data_file=False) == []
    text = "\n".join(["::: {.dat-like}", chunk("head(df)"), ":::"])
    assert found(text, data_file=False) == []


def test_div_fence_inside_a_code_chunk_is_not_a_div():
    text = "\n".join(["```{r}", "::: {#dat-x}", "```", chunk("head(df)")])
    assert found(text, data_file=False) == []


@pytest.mark.parametrize("rel, expected", [
    ("chapters/_subfiles/x/_dat-auto.qmd", True),
    ("chapters/_subfiles/x/_dat-auto-preview.qmd", True),
    ("_dat-auto.qmd", True),
    ("chapters/_subfiles/x/_exm-auto.qmd", False),
    ("chapters/_dat-x/page.qmd", False),
])
def test_data_file_names(rel, expected):
    assert crh.is_data_file(rel, ["_dat-*"]) is expected


# -- the allow comment ----------------------------------------------------------

def test_allow_comment_with_a_reason_on_the_line():
    assert found(chunk("head(df)  # check-r-head: allow: wide table")) == []


def test_allow_comment_on_the_line_before():
    assert found(chunk("# check-r-head: allow: wide table", "head(df)")) == []


def test_allow_comment_needs_a_reason():
    assert found(chunk("head(df)  # check-r-head: allow:")) == [2]
    assert found(chunk("head(df)  # check-r-head: allow")) == [2]


def test_allow_comment_covers_one_statement_only():
    text = chunk("# check-r-head: allow: demo", "head(df)", "head(df2)")
    assert found(text) == [4]


# -- helpers ----------------------------------------------------------------------

def test_strip_r_line_blanks_strings_and_cuts_comments():
    assert crh.strip_r_line('x <- "a#b" # c') == 'x <- "   " '
    assert crh.strip_r_line("y <- 'it\\'s'") == "y <- '     '"


def test_message_names_df_print():
    msg = crh.format_message(crh.Finding(1, (1,)))
    assert "df-print" in msg and "paged" in msg and "tibble" in msg


# -- diff scoping ----------------------------------------------------------------

def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t",
                    "-c", "user.email=t@example.com", *args],  # phi-allow
                   check=True, capture_output=True)


BASE = chunk("old <- 1", "head(old_df)", "df") + "\n"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "_dat-x.qmd").write_text(BASE)
    (tmp_path / "page.qmd").write_text(chunk("x") + "\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "base")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _run(base_ref="HEAD", whole_tree=False, data_files=None):
    ignores = crh.compile_globs([])
    return crh.run_check(base_ref, ["*.qmd"], ignores, whole_tree, data_files)


def _lines(report):
    return [(rel, f.line) for rel, f in report.findings]


def test_existing_head_in_an_untouched_line_is_not_reported(repo):
    (repo / "_dat-x.qmd").write_text(BASE + "New text.\n")
    report = _run()
    assert report.findings == [] and not report.skipped


def test_added_head_is_reported(repo):
    (repo / "_dat-x.qmd").write_text(BASE + chunk("df |> head()") + "\n")
    assert _lines(_run()) == [("_dat-x.qmd", 7)]


def test_added_head_outside_a_data_file_is_not_reported(repo):
    (repo / "page.qmd").write_text(chunk("x", "head(df)") + "\n")
    assert _run().findings == []


def test_added_line_of_an_old_statement_reports_it(repo):
    (repo / "_dat-x.qmd").write_text(
        chunk("old <- 1", "head(old_df,", "  3)", "df") + "\n")
    assert _lines(_run()) == [("_dat-x.qmd", 3)]


def test_moved_line_is_not_new(repo):
    (repo / "_dat-x.qmd").write_text(
        chunk("old <- 1", "df") + "\n\nText.\n\n" + chunk("head(old_df)") + "\n")
    assert _run().findings == []


def test_added_line_of_a_statement_without_head_on_it_reports_it(repo):
    (repo / "_dat-x.qmd").write_text(chunk("head(", "  old_df", ")") + "\n")
    _git(repo, "commit", "-q", "-am", "multi-line call")
    (repo / "_dat-x.qmd").write_text(chunk("head(", "  new_df", ")") + "\n")
    assert _lines(_run()) == [("_dat-x.qmd", 2)]


def test_braces_then_a_semicolon_split_at_top_level():
    assert found(chunk("if (TRUE) { a <- 1 }; head(df)")) == [2]


def test_data_files_is_configurable(repo):
    (repo / "page.qmd").write_text(chunk("x", "head(df)") + "\n")
    assert _lines(_run(data_files=["page.*"])) == [("page.qmd", 3)]


def test_whole_tree_reports_the_existing_head(repo):
    assert _lines(_run(whole_tree=True)) == [("_dat-x.qmd", 3)]


def test_no_base_ref_skips_instead_of_scanning(repo):
    assert _run(base_ref="").skipped


def test_unresolvable_base_ref_skips(repo):
    assert _run(base_ref="no-such-ref").skipped


# -- main() ----------------------------------------------------------------------

def test_main_blocks_by_default(repo, monkeypatch, capsys):
    (repo / "_dat-x.qmd").write_text(chunk("head(df)") + "\n")
    monkeypatch.setenv("CRH_BASE_REF", "HEAD")
    monkeypatch.delenv("CRH_FAIL", raising=False)
    assert crh.main() == 1
    assert "::error file=_dat-x.qmd,line=2::" in capsys.readouterr().out


def test_main_warns_when_fail_is_false(repo, monkeypatch, capsys):
    (repo / "_dat-x.qmd").write_text(chunk("head(df)") + "\n")
    monkeypatch.setenv("CRH_BASE_REF", "HEAD")
    monkeypatch.setenv("CRH_FAIL", "false")
    assert crh.main() == 0
    assert "::warning file=_dat-x.qmd,line=2::" in capsys.readouterr().out


def test_main_reads_data_files(repo, monkeypatch):
    (repo / "page.qmd").write_text(chunk("head(df)") + "\n")
    monkeypatch.setenv("CRH_BASE_REF", "HEAD")
    monkeypatch.setenv("CRH_DATA_FILES", "other-*, page.qmd")
    assert crh.main() == 1


def test_main_skips_without_a_base(repo, monkeypatch):
    (repo / "_dat-x.qmd").write_text(chunk("head(df)") + "\n")
    monkeypatch.delenv("CRH_BASE_REF", raising=False)
    assert crh.main() == 0


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
          _ROOT / ".github" / "workflows" / "check-r-head.yml"]


@pytest.mark.parametrize("path", _FILES, ids=lambda p: p.name)
def test_defaults_agree_with_the_script(path):
    assert _default(path, "globs") == crh.DEFAULT_GLOBS
    assert _default(path, "data-files") == crh.DEFAULT_DATA_FILES
    assert _default(path, "fail") == str(crh._DEFAULT_FAIL).lower()
