"""Unit tests for check-self-credits.

Covers the config parser, the bibliography reader, what counts as a credit to
the group's own work (a citation of an own entry, a credit phrase beside an own
name in one paragraph or Source div), what is not flagged (a bare link for
further reading, an outside person's credit, an allowed key, code), diff
scoping, and the defaults the action, the reusable workflow and the script must
agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_self_credits", _DIR / "check-self-credits.py"
)
assert _spec is not None and _spec.loader is not None
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)

CONFIG = """\
urls:
  - morrison-lab.github.io   # the group's sites
  - ucd-serg.github.io/lab-manual
names: [Morrison-Lab/sds, "UCD-SERG lab manual"]
authors:
  - Morrison, Ezra
keys: [forcedown]
allow-keys: [morrison2026paper]
allow-patterns:
  - 'nocredit'
"""

BIB = """\
@book{morrison2026mds,
  author = {Morrison, Ezra},
  title  = {Math for Data Science},
  url    = {https://morrison-lab.github.io/mds/}
}
@article{morrison2026paper,
  author = {Morrison, Ezra and Other, A.},
  title  = {A published paper},
  doi    = {10.1000/xyz}
}
@book{hutchinson2020,
  author = {Hutchinson, Brian},
  title  = {Notes}
}
@misc{forcedown,
  author = {Someone},
  title  = {Listed by key}
}
@misc{manual,
  author = {{UCD-SERG}},
  howpublished = {Online manual},
  url = {https://ucd-serg.github.io/lab-manual/writing.html}
}
"""


@pytest.fixture
def cfg():
    lists = sc.parse_lists(CONFIG)
    return sc.Config(
        urls=[u.lower() for u in lists["urls"]],
        names=lists["names"],
        authors=[a.lower() for a in lists["authors"]],
        keys=set(lists["keys"]),
        allow_keys=set(lists["allow-keys"]),
        allow_patterns=[__import__("re").compile(p) for p in lists["allow-patterns"]],
        bib_globs=["*.bib"],
    )


@pytest.fixture
def own(cfg):
    return sc.own_keys(sc.parse_bib(BIB), cfg)


def flagged(text, cfg, own):
    found, _ = sc.scan_file(text.split("\n"), cfg, own)
    return [(f.line, f.kind) for f in found]


# -- Config and bibliography -------------------------------------------------

def test_parse_lists_block_inline_and_comments():
    lists = sc.parse_lists(CONFIG)
    assert lists["urls"] == ["morrison-lab.github.io", "ucd-serg.github.io/lab-manual"]
    assert lists["names"] == ["Morrison-Lab/sds", "UCD-SERG lab manual"]
    assert lists["keys"] == ["forcedown"]


def test_parse_bib_fields():
    entries = sc.parse_bib(BIB)
    assert set(entries) == {"morrison2026mds", "morrison2026paper", "hutchinson2020",
                            "forcedown", "manual"}
    assert entries["manual"]["author"] == "{UCD-SERG}"
    assert entries["morrison2026mds"]["url"].startswith("https://morrison-lab")


def test_own_keys_by_url_author_key_minus_allowed(own):
    assert own == {"morrison2026mds", "forcedown", "manual"}


def test_outside_author_is_not_own(own):
    assert "hutchinson2020" not in own


# -- What is flagged ---------------------------------------------------------

def test_bracketed_citation_of_own_entry(cfg, own):
    assert flagged("The bound holds [@morrison2026mds].", cfg, own) == [(1, "citation")]


def test_bare_citation_of_own_entry(cfg, own):
    assert flagged("As @manual explains, write early.", cfg, own) == [(1, "citation")]


def test_citation_by_key_list(cfg, own):
    assert flagged("See [@hutchinson2020; @forcedown, p. 3].", cfg, own) == [(1, "citation")]


def test_adapted_from_beside_own_site(cfg, own):
    text = "This section is adapted from the Morrison-Lab/sds notes."
    assert flagged(text, cfg, own) == [(1, "credit")]


def test_credit_phrase_and_name_in_one_paragraph(cfg, own):
    text = "This example is based on\nthe UCD-SERG lab manual.\n"
    assert flagged(text, cfg, own) == [(2, "credit")]


def test_source_line_naming_own_site(cfg, own):
    text = "Source: https://morrison-lab.github.io/mds/page.html"
    assert flagged(text, cfg, own) == [(1, "credit")]


def test_source_div_naming_own_site(cfg, own):
    text = (
        '::: {.callout-note title="Source"}\n'
        "See the UCD-SERG lab manual for the original.\n"
        ":::\n"
    )
    assert flagged(text, cfg, own) == [(2, "credit")]


# -- What is not flagged -----------------------------------------------------

def test_bare_link_for_further_reading(cfg, own):
    text = "For further reading, see the [sds notes](https://morrison-lab.github.io/sds/)."
    assert flagged(text, cfg, own) == []


def test_outside_person_credit(cfg, own):
    text = "Adapted from Hutchinson's notes [@hutchinson2020]."
    assert flagged(text, cfg, own) == []


def test_allowed_key_is_not_flagged(cfg, own):
    assert flagged("We use the method of [@morrison2026paper].", cfg, own) == []


def test_credit_phrase_in_other_paragraph(cfg, own):
    text = "This is adapted from a textbook.\n\nSee the UCD-SERG lab manual.\n"
    assert flagged(text, cfg, own) == []


def test_source_div_closed_before_later_paragraph(cfg, own):
    text = (
        '::: {.callout-note title="Source"}\n'
        "Outside source.\n"
        ":::\n"
        "\n"
        "See the UCD-SERG lab manual.\n"
    )
    assert flagged(text, cfg, own) == []


def test_cross_reference_prefix_is_not_a_citation(cfg, own):
    assert flagged("See @def-forcedown.", cfg, own) == []


def test_code_fence_and_chunk_options_skipped(cfg, own):
    text = "```{r}\n#| label: [@forcedown]\nx <- '[@forcedown]'\n```\n"
    assert flagged(text, cfg, own) == []


def test_allow_pattern_line_skipped(cfg, own):
    assert flagged("nocredit [@forcedown]", cfg, own) == []


def test_email_is_not_a_citation(cfg, own):
    assert flagged("Write to me@forcedown.org.", cfg, own) == []  # phi-allow


# -- Diff scoping ------------------------------------------------------------

def test_parse_diff_added_and_deleted():
    diff = (
        "diff --git a/a.qmd b/a.qmd\n--- a/a.qmd\n+++ b/a.qmd\n"
        "@@ -1,1 +1,2 @@\n-old\n+new [@forcedown]\n+kept\n"
    )
    added, deleted = sc.parse_diff(diff)
    assert added == {"a.qmd": {1: "new [@forcedown]", 2: "kept"}}
    assert deleted == {"old"}


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _repo(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")  # phi-allow
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "references.bib").write_text(BIB)
    (tmp_path / "a.qmd").write_text("Old credit [@forcedown].\nText.\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    _git(tmp_path, "checkout", "-q", "-b", "pr")
    return tmp_path


def test_only_added_lines_are_reported(tmp_path, monkeypatch, cfg):
    repo = _repo(tmp_path)
    (repo / "a.qmd").write_text("Old credit [@forcedown].\nText.\nNew [@morrison2026mds].\n")
    _git(repo, "commit", "-qam", "pr")
    monkeypatch.chdir(repo)
    report = sc.run_check("main", ["*.qmd", "*.md"], [], False, cfg)
    assert not report.skipped
    assert [(rel, f.line) for rel, f in report.findings] == [("a.qmd", 3)]
    assert report.entries == 5 and report.own == 3


def test_moved_line_is_not_new(tmp_path, monkeypatch, cfg):
    repo = _repo(tmp_path)
    (repo / "a.qmd").write_text("Text.\nOld credit [@forcedown].\n")
    _git(repo, "commit", "-qam", "move")
    monkeypatch.chdir(repo)
    report = sc.run_check("main", ["*.qmd"], [], False, cfg)
    assert report.findings == []


def test_whole_tree_reports_everything(tmp_path, monkeypatch, cfg):
    repo = _repo(tmp_path)
    monkeypatch.chdir(repo)
    report = sc.run_check("", ["*.qmd"], [], True, cfg)
    assert [(rel, f.line) for rel, f in report.findings] == [("a.qmd", 1)]


def test_no_base_ref_skips(tmp_path, monkeypatch, cfg):
    repo = _repo(tmp_path)
    monkeypatch.chdir(repo)
    assert sc.run_check("", ["*.qmd"], [], False, cfg).skipped


def test_paths_ignore(tmp_path, monkeypatch, cfg):
    repo = _repo(tmp_path)
    monkeypatch.chdir(repo)
    ignores = sc.compile_ignores(["a.qmd"])
    report = sc.run_check("", ["*.qmd"], ignores, True, cfg)
    assert report.findings == []


def test_load_config_missing_file_returns_none(tmp_path):
    assert sc.load_config(str(tmp_path / "none.yml")) is None


# -- Defaults the three files must agree on ----------------------------------

def test_defaults_agree():
    action = (_DIR / "action.yml").read_text()
    workflow = (_DIR.parent / ".github" / "workflows" / "check-self-credits.yml").read_text()
    assert sc.DEFAULT_GLOBS == "*.qmd *.md"
    assert sc.DEFAULT_CONFIG == ".github/own-works.yml"
    assert sc._DEFAULT_FAIL is False
    for text in (action, workflow):
        assert "'*.qmd *.md'" in text
        assert "'.github/own-works.yml'" in text
    assert "default: 'false'" in action
