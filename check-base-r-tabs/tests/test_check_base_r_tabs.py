"""Unit tests for check-base-r-tabs.

Covers what is flagged (a panel-tabset with an "R (tidymodels)" tab and no
base R tab), what is not (a base R sibling under any accepted heading, no
tidymodels tab, headings in code fences or nested divs, the opt-out comment),
diff scoping through ``main()``, and the defaults the script, the action and
the reusable workflow must agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_base_r_tabs", _DIR / "check-base-r-tabs.py"
)
assert _spec is not None and _spec.loader is not None
cbr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cbr)


def flagged(text: str):
    return [h for h, _s, _e in cbr.missing_base_r(text.split("\n"))]


def tabset(*headings: str, level: str = "###", extra: str = "") -> str:
    body = "\n\n".join(f"{level} {h}\n\n```{{r}}\nx <- 1\n```" for h in headings)
    return f"::: {{.panel-tabset}}\n\n{extra}{body}\n\n:::"


def test_tidymodels_without_base_r_is_flagged_at_its_heading():
    text = tabset("Python", "R (tidymodels)")
    assert flagged(text) == [text.split("\n").index("### R (tidymodels)") + 1]


@pytest.mark.parametrize("base", ["R", "Base R", "R (base)", "R (base R)", "r"])
def test_a_base_r_sibling_passes(base):
    assert flagged(tabset("Python", base, "R (tidymodels)")) == []


@pytest.mark.parametrize("heading", ["R (Tidymodels)", "R (tidymodels) {#tab-a}",
                                     "R ( tidymodels )"])
def test_tidymodels_heading_variants_are_flagged(heading):
    assert len(flagged(tabset("Python", heading))) == 1


def test_no_tidymodels_tab_is_not_flagged():
    assert flagged(tabset("Python", "R")) == []
    assert flagged(tabset("Python", "Julia")) == []


def test_tabset_with_group_attribute_is_recognized():
    text = '::: {.panel-tabset group="language"}\n\n## R (tidymodels)\n\nx\n\n:::'
    assert len(flagged(text)) == 1


def test_r_heading_outside_the_tabset_does_not_count():
    text = "### R\n\nprose\n\n" + tabset("Python", "R (tidymodels)")
    assert len(flagged(text)) == 1


def test_r_heading_after_the_tabset_closes_does_not_count():
    text = tabset("Python", "R (tidymodels)") + "\n\n### R\n\nprose"
    assert len(flagged(text)) == 1


def test_heading_in_a_code_fence_is_ignored():
    fenced = "```markdown\n### R\n```\n\n"
    assert len(flagged(tabset("Python", "R (tidymodels)", extra=fenced))) == 1
    fenced_tidy = "```markdown\n### R (tidymodels)\n```\n\n"
    assert flagged(tabset("Python", "R", extra=fenced_tidy)) == []


def test_deeper_heading_inside_a_tab_is_not_a_tab():
    text = ("::: {.panel-tabset}\n\n### Python\n\n#### R\n\nx\n\n"
            "### R (tidymodels)\n\ny\n\n:::")
    assert len(flagged(text)) == 1


def test_heading_in_a_nested_div_is_not_a_tab():
    text = ("::: {.panel-tabset}\n\n### Python\n\n:::: {.callout-note}\n"
            "### R\n::::\n\n### R (tidymodels)\n\ny\n\n:::")
    assert len(flagged(text)) == 1


def test_nested_tabsets_are_judged_separately():
    inner = ":::: {.panel-tabset}\n\n#### R (tidymodels)\n\nz\n\n::::"
    text = (f"::: {{.panel-tabset}}\n\n### R\n\n{inner}\n\n"
            "### R (tidymodels)\n\ny\n\n:::")
    assert len(flagged(text)) == 1


def test_opt_out_needs_a_reason():
    with_reason = "<!-- base-r-tab: none: no base R function fits this -->\n\n"
    assert flagged(tabset("Python", "R (tidymodels)", extra=with_reason)) == []
    without = "<!-- base-r-tab: none: -->\n\n"
    assert len(flagged(tabset("Python", "R (tidymodels)", extra=without))) == 1


def test_two_offending_tabsets_give_two_findings():
    text = tabset("Python", "R (tidymodels)") + "\n\n" + tabset("R (tidymodels)")
    assert len(flagged(text)) == 2


# --- main(): diff scoping --------------------------------------------------

def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True,
                          capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path, monkeypatch):
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.name", "t")
    git(tmp_path, "config", "user.email", "t@example.com")  # phi-allow
    (tmp_path / "old.qmd").write_text(tabset("Python", "R (tidymodels)") + "\n")
    (tmp_path / "keep.qmd").write_text("prose\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "base")
    git(tmp_path, "tag", "base")
    monkeypatch.chdir(tmp_path)
    for name in ("CBR_BASE_REF", "CBR_GLOBS", "CBR_FAIL", "CBR_WHOLE_TREE"):
        monkeypatch.delenv(name, raising=False)
    return tmp_path


def commit(repo: Path, name: str, text: str) -> None:
    (repo / name).write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "change")


def test_untouched_offending_tabset_passes(repo, monkeypatch):
    commit(repo, "keep.qmd", "prose\nmore prose\n")
    monkeypatch.setenv("CBR_BASE_REF", "base")
    assert cbr.main() == 0


def test_new_offending_tabset_fails(repo, monkeypatch, capsys):
    commit(repo, "new.qmd", tabset("Python", "R (tidymodels)") + "\n")
    monkeypatch.setenv("CBR_BASE_REF", "base")
    assert cbr.main() == 1
    assert "file=new.qmd" in capsys.readouterr().out


def test_edit_inside_an_old_offending_tabset_fails(repo, monkeypatch):
    text = (repo / "old.qmd").read_text().replace("x <- 1", "x <- 2", 1)
    commit(repo, "old.qmd", text)
    monkeypatch.setenv("CBR_BASE_REF", "base")
    assert cbr.main() == 1


def test_adding_the_base_r_tab_passes(repo, monkeypatch):
    commit(repo, "old.qmd", tabset("Python", "R", "R (tidymodels)") + "\n")
    monkeypatch.setenv("CBR_BASE_REF", "base")
    assert cbr.main() == 0


def test_warn_only_mode_returns_zero(repo, monkeypatch):
    commit(repo, "new.qmd", tabset("R (tidymodels)") + "\n")
    monkeypatch.setenv("CBR_BASE_REF", "base")
    monkeypatch.setenv("CBR_FAIL", "false")
    assert cbr.main() == 0


def test_no_base_ref_skips(repo):
    assert cbr.main() == 0


def test_whole_tree_flags_the_old_tabset(repo, monkeypatch):
    monkeypatch.setenv("CBR_WHOLE_TREE", "true")
    assert cbr.main() == 1


# --- defaults agree ---------------------------------------------------------

def yaml_default(path: Path, name: str) -> str:
    lines = path.read_text().split("\n")
    for i, line in enumerate(lines):
        if line.strip() == f"{name}:":
            for follow in lines[i + 1:i + 12]:
                if follow.strip().startswith("default:"):
                    return follow.split(":", 1)[1].strip().strip("'\"")
    raise AssertionError(f"no default for {name} in {path}")


@pytest.mark.parametrize("path", [
    _DIR / "action.yml",
    _DIR.parent / ".github" / "workflows" / "check-base-r-tabs.yml",
])
def test_defaults_agree(path):
    assert yaml_default(path, "globs") == cbr.DEFAULT_GLOBS
    assert yaml_default(path, "fail") == "true"
