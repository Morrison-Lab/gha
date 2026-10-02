"""Unit tests for check-quarto-prose.

Each detector gets a positive case and the negative cases that stop it from
passing vacuously. The negatives are the ones to keep if this is ever
trimmed, because each pins a decision that is silent when reversed:

  * a banned phrase inside a nested code fence (a longer outer fence holding
    a shorter one) passes, and the same phrase after the fence closes does not
  * a notes div with plain commentary passes
  * an example div AFTER a notes div closes passes (colon-run depth tracking)
  * `<!-- prose-allow: ... -->` exempts only the phrase it names
  * an empty base-ref SKIPS rather than scanning the whole tree
  * a banned phrase on an untouched line is not reported, one on an added line is
  * a missing or empty idioms file is an error, not a pass

check-quarto-prose.py is not an importable name (the hyphen), so load it by
path, as the sibling checks' tests do.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_SCRIPT = _DIR / "check-quarto-prose.py"
_ACTION_YML = _DIR / "action.yml"
_WORKFLOW_YML = _DIR.parent / ".github" / "workflows" / "check-quarto-prose.yml"
_spec = importlib.util.spec_from_file_location("check_quarto_prose", _SCRIPT)
assert _spec is not None and _spec.loader is not None, f"Could not load {_SCRIPT}"
cqp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cqp)

_IDIOMS = cqp.load_idioms(_DIR / "banned-idioms.txt")


def scan(text: str, path: str = "page.qmd", idioms=None, allow=None):
    return cqp.scan_text(path, textwrap.dedent(text), idioms or _IDIOMS, allow or [])


def rules(findings) -> list[tuple[str, int]]:
    return [(f.rule, f.line) for f in findings]


# --------------------------------------------------------------- notes divs


def test_notes_div_with_nested_example_div_is_flagged() -> None:
    found = scan(
        """\
        ::: notes
        Talk through the plot.

        ::: {#exm-coin}
        A fair coin.
        :::
        :::
        """
    )
    assert rules(found) == [(cqp.RULE_NOTES, 4)]
    assert "Use an #exm-, #rem- or #def- div, not a notes div." in found[0].message


@pytest.mark.parametrize("prefix", ["exm", "rem", "def", "thm", "exr"])
def test_every_theorem_prefix_is_flagged(prefix: str) -> None:
    found = scan(f"::: {{.notes}}\nSay hello.\n\n::: {{#{prefix}-x}}\nbody\n:::\n:::\n")
    assert rules(found) == [(cqp.RULE_NOTES, 4)]


def test_other_id_prefix_inside_notes_passes() -> None:
    assert scan("::: notes\nSay hello.\n\n::: {#fig-x}\nbody\n:::\n:::\n") == []


@pytest.mark.parametrize(
    "first_line",
    [
        "Example 2. A coin.",
        "**Example 2.** A coin.",
        "__Remark.__ This holds.",
        "*Remark* this holds.",
        "remark: lower case",
        "Note: read this aloud.",
        "**Note:** read this aloud.",
        "**Note**: read this aloud.",
    ],
)
def test_notes_div_first_line_is_flagged(first_line: str) -> None:
    found = scan(f"::: notes\n\n{first_line}\n:::\n")
    assert rules(found) == [(cqp.RULE_NOTES, 3)]


def test_notes_div_with_plain_commentary_passes() -> None:
    text = """\
        ::: notes
        Pause here and ask the room what they expect.
        Note that the next slide repeats the table.
        An example of this appears later, but not in these notes.
        :::
        """
    assert scan(text) == []


def test_only_the_first_nonblank_line_is_tested() -> None:
    assert scan("::: notes\nSay hello.\nExample: not first.\n:::\n") == []


def test_example_div_outside_notes_passes() -> None:
    assert scan("::: {#exm-coin}\nExample: a coin.\n:::\n") == []


def test_example_div_after_notes_closes_passes() -> None:
    """Depth tracking: the notes div is closed, so the next div is not in it."""
    text = """\
        ::: notes
        Say hello.
        :::

        ::: {#exm-after}
        Body.
        :::
        """
    assert scan(text) == []


def test_longer_outer_fence_nesting_is_tracked_by_colon_run() -> None:
    text = """\
        ::::: notes
        Say hello.

        ::: {.callout-note}
        Plain callout.
        :::

        ::: {#rem-in}
        A remark.
        :::
        :::::

        ::: {#rem-out}
        Outside the notes div.
        :::
        """
    assert rules(scan(text)) == [(cqp.RULE_NOTES, 8)]


def test_same_length_nesting_closes_the_innermost_div() -> None:
    text = """\
        ::: notes
        Say hello.

        ::: {.callout-note}
        Plain.
        :::

        ::: {#exm-in}
        Inside the notes div.
        :::
        :::

        ::: {#exm-out}
        Outside.
        :::
        """
    assert rules(scan(text)) == [(cqp.RULE_NOTES, 8)]


def test_longer_closing_fence_closes_an_unclosed_inner_div() -> None:
    text = """\
        :::: notes
        Say hello.
        ::: {.callout-note}
        Forgot to close this one.
        ::::

        ::: {#exm-out}
        Outside.
        :::
        """
    assert scan(text) == []


def test_notes_div_inside_code_fence_is_ignored() -> None:
    text = """\
        ````markdown
        ::: notes
        ::: {#exm-x}
        body
        :::
        :::
        ````
        """
    assert scan(text) == []


def test_notes_div_inside_comment_and_math_is_ignored() -> None:
    text = """\
        <!--
        ::: notes
        ::: {#exm-x}
        -->

        $$
        ::: notes
        ::: {#exm-x}
        $$
        """
    assert scan(text) == []


# ------------------------------------------------------------ banned idioms


def test_banned_phrase_is_flagged_case_insensitively_with_its_line() -> None:
    found = scan("Plain line.\n\nWe look UNDER THE HOOD here.\n")
    assert rules(found) == [(cqp.RULE_IDIOM, 3)]
    assert "UNDER THE HOOD" in found[0].message


def test_whole_phrase_only() -> None:
    assert scan("Under the hoodie, underthehood, and the thunder the hood.\n") == []


def test_wildcard_covers_inflections() -> None:
    found = scan("We cherry-picked, cherry pick, and are cherry-picking.\n")
    assert len(found) == 3


def test_bare_lean_is_not_banned_but_the_figurative_forms_are() -> None:
    assert scan("Lean statistics and a lean model.\n") == []
    assert len(scan("Which way does this course lean?\n")) == 1
    assert len(scan("The text leans toward theory.\n")) == 1


def test_hyphen_and_space_are_interchangeable() -> None:
    assert len(scan("A hand wavy claim.\n")) == 1
    assert len(scan("A hand-wavy claim.\n")) == 1
    assert len(scan("A back-of-the-envelope estimate.\n")) == 1


def test_phrase_wrapped_across_a_line_break_is_found_at_its_first_line() -> None:
    found = scan("We look under the\nhood now.\n")
    assert [(f.line, f.end_line) for f in found] == [(1, 2)]


def test_phrase_does_not_span_a_blank_line() -> None:
    assert scan("We look under the\n\nhood now.\n") == []


def test_phrase_does_not_span_a_masked_code_span() -> None:
    assert scan("We look under the `x` hood now.\n") == []


def test_overlapping_entries_report_once() -> None:
    assert len(scan("Give a ballpark figure.\n")) == 1


def test_nested_code_fence_holding_the_phrase_passes() -> None:
    """The negative that keeps the fence tracking honest: a four-backtick
    fence holding a three-backtick fence stays open until its own closer."""
    text = """\
        ````text
        ```
        under the hood
        ```
        under the hood
        ````
        """
    assert scan(text) == []


def test_phrase_after_the_fence_closes_is_flagged() -> None:
    text = """\
        ````text
        ```
        under the hood
        ```
        ````
        Now under the hood.
        """
    assert rules(scan(text)) == [(cqp.RULE_IDIOM, 6)]


def test_tilde_fence_and_chunk_are_skipped() -> None:
    text = """\
        ```{r}
        # under the hood
        ```

        ~~~
        deep dive
        ~~~
        """
    assert scan(text) == []


def test_mismatched_fence_character_does_not_close() -> None:
    text = """\
        ```
        ~~~
        under the hood
        ```
        """
    assert scan(text) == []


def test_inline_code_math_and_comments_are_skipped() -> None:
    text = """\
        Use `under the hood` here, or ``a `deep dive` b``.
        The value $deep dive$ and $$under the hood$$ are math.
        <!-- under the hood -->
        <!--
        deep dive
        -->
        """
    assert scan(text) == []


def test_display_math_block_is_skipped() -> None:
    assert scan("$$\nunder the hood\n$$\n") == []


def test_dollar_amounts_are_not_math() -> None:
    assert len(scan("It costs $5 and $10, under the hood.\n")) == 1


def test_links_urls_ids_citations_and_shortcodes_are_skipped() -> None:
    text = """\
        # Heading {#sec-deep-dive}

        See [the page](deep-dive.qmd) and https://example.com/deep-dive.
        Cite @deep-dive2020 and {{< include _deep-dive.qmd >}}.
        ![](under-the-hood.png){width=50%}
        <img src="deep-dive.png" alt="x">
        [ref]: https://example.com/under-the-hood
        """
    assert scan(text) == []


def test_link_text_is_still_scanned() -> None:
    assert len(scan("See [a deep dive](x.qmd).\n")) == 1


def test_front_matter_scans_only_title_subtitle_and_description() -> None:
    text = """\
        ---
        title: A deep dive
        subtitle: "Under the hood"
        description: >-
          Rule of thumb
          for all.
        author: Deep Dive
        keywords: [under the hood]
        categories:
          - game changer
        ---
        Body.
        """
    assert rules(scan(text)) == [
        (cqp.RULE_IDIOM, 2),
        (cqp.RULE_IDIOM, 3),
        (cqp.RULE_IDIOM, 5),
    ]


def test_unclosed_front_matter_is_treated_as_body() -> None:
    assert len(scan("---\nunder the hood\n")) == 1


def test_curly_apostrophe_matches(tmp_path: Path) -> None:
    list_file = tmp_path / "list.txt"
    list_file.write_text("don't hold your breath\n", encoding="utf-8")
    idioms = cqp.load_idioms(list_file)
    curly = chr(0x2019)
    assert len(scan(f"Please don{curly}t hold your breath.\n", idioms=idioms)) == 1


# -------------------------------------------------------------------- allow


def test_allow_comment_on_the_same_line_exempts_that_phrase_only() -> None:
    text = "A rule of thumb and a deep dive <!-- prose-allow: rule of thumb -->\n"
    found = scan(text)
    assert len(found) == 1
    assert "deep dive" in found[0].message


def test_allow_comment_alone_exempts_the_next_line_only() -> None:
    text = """\
        <!-- prose-allow: rule of thumb -->
        He called it a "rule of thumb".
        Another rule of thumb here.
        """
    assert rules(scan(text)) == [(cqp.RULE_IDIOM, 3)]


def test_allow_comment_lists_several_phrases() -> None:
    text = "Both rule of thumb and deep dive. <!-- prose-allow: rule of thumb, deep dive -->\n"
    assert scan(text) == []


def test_allow_comment_inside_code_is_not_an_allowance() -> None:
    text = "Write `<!-- prose-allow: rule of thumb -->` for a rule of thumb.\n"
    assert len(scan(text)) == 1


def test_allow_comment_matches_the_inflected_text_too() -> None:
    assert scan("It was cherry-picked. <!-- prose-allow: cherry-picked -->\n") == []
    assert scan("It was cherry-picked. <!-- prose-allow: cherry-pick -->\n") == []


def test_allow_file_exempts_by_path_glob_and_phrase(tmp_path: Path) -> None:
    allow_file = tmp_path / "allow.txt"
    allow_file.write_text(
        "# quoted on purpose\nquotes/**: rule of thumb\ndeep dive\n", encoding="utf-8"
    )
    allow = cqp.load_allow(allow_file)
    text = "A rule of thumb and a deep dive.\n"
    assert scan(text, path="quotes/a.qmd", allow=allow) == []
    other = scan(text, path="notes/a.qmd", allow=allow)
    assert len(other) == 1 and "rule of thumb" in other[0].message


# ----------------------------------------------------------- the idiom list


def test_default_list_is_well_formed_and_every_entry_matches_itself() -> None:
    assert len(_IDIOMS) >= 40
    norms = [i.norm for i in _IDIOMS]
    assert len(norms) == len(set(norms))
    for idiom in _IDIOMS:
        sample = idiom.text.replace("*", "")
        assert idiom.regex.search(f"x {sample} y"), idiom.text


def test_empty_idioms_file_is_an_error(tmp_path: Path) -> None:
    empty = tmp_path / "empty.txt"
    empty.write_text("# only a comment\n\n", encoding="utf-8")
    with pytest.raises(ValueError, match="lists no phrases"):
        cqp.load_idioms(empty)


def test_bare_star_word_is_an_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.txt"
    bad.write_text("under * hood\n", encoding="utf-8")
    with pytest.raises(ValueError, match="only '\\*'"):
        cqp.load_idioms(bad)


# ------------------------------------------------------ driver and scoping


def _init_repo(root: Path) -> Path:
    for args in (
        ["init", "-q", "-b", "main"],
        ["config", "user.email", "t@example.invalid"],
        ["config", "user.name", "t"],
        ["config", "commit.gpgsign", "false"],
    ):
        subprocess.run(["git", *args], cwd=root, check=True)
    return root


def _commit(root: Path, message: str) -> str:
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=root, check=True)
    return _head(root)


def _head(root: Path) -> str:
    out = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    )
    return out.stdout.strip()


def _run(root: Path, **env: str) -> subprocess.CompletedProcess[str]:
    full_env = {k: v for k, v in os.environ.items() if not k.startswith("CQP_")}
    full_env["CQP_TARGET"] = str(root)
    full_env.update({f"CQP_{k.upper()}": v for k, v in env.items()})
    return subprocess.run(
        [sys.executable, str(_SCRIPT)],
        cwd=root,
        env=full_env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repo with one page carrying a banned phrase on a line that predates the PR."""
    _init_repo(tmp_path)
    (tmp_path / "page.qmd").write_text(
        "# Page\n\nThis is a deep dive, written long ago.\n", encoding="utf-8"
    )
    _commit(tmp_path, "base")
    return tmp_path


def test_empty_base_ref_skips_rather_than_scanning_the_tree(repo: Path) -> None:
    result = _run(repo)
    assert result.returncode == 0
    assert "Skipping the prose check" in result.stdout
    assert "::error" not in result.stdout


def test_unresolvable_base_ref_skips(repo: Path) -> None:
    result = _run(repo, base_ref="0" * 40)
    assert result.returncode == 0
    assert "Skipping the prose check" in result.stdout


def test_existing_phrase_on_an_untouched_line_is_not_reported(repo: Path) -> None:
    base = _head(repo)
    with (repo / "page.qmd").open("a", encoding="utf-8") as fh:
        fh.write("A clean added line.\n")
    _commit(repo, "clean edit")
    result = _run(repo, base_ref=base)
    assert result.returncode == 0, result.stdout
    assert "No prose findings." in result.stdout
    assert "ignored (existing prose)" in result.stdout


def test_added_phrase_is_reported_with_file_and_line(repo: Path) -> None:
    base = _head(repo)
    with (repo / "page.qmd").open("a", encoding="utf-8") as fh:
        fh.write("We move the needle here.\n")
    _commit(repo, "bad edit")
    result = _run(repo, base_ref=base)
    assert result.returncode == 1
    assert "::error file=page.qmd,line=4::banned-idiom:" in result.stdout
    assert "line=3" not in result.stdout


def test_added_notes_example_is_reported(repo: Path) -> None:
    base = _head(repo)
    (repo / "slides.qmd").write_text(
        "::: notes\n**Example 1.** A coin.\n:::\n", encoding="utf-8"
    )
    _commit(repo, "notes edit")
    result = _run(repo, base_ref=base)
    assert result.returncode == 1
    assert "::error file=slides.qmd,line=2::notes-div-content:" in result.stdout


def test_base_ref_all_scans_every_tracked_file(repo: Path) -> None:
    result = _run(repo, base_ref="all")
    assert result.returncode == 1
    assert "::error file=page.qmd,line=3::banned-idiom:" in result.stdout


def test_globs_and_paths_ignore_limit_the_scan(repo: Path) -> None:
    assert _run(repo, base_ref="all", globs="*.md").returncode == 0
    assert _run(repo, base_ref="all", paths_ignore="page.qmd").returncode == 0


def test_only_md_and_qmd_are_scanned_by_default(repo: Path) -> None:
    (repo / "notes.txt").write_text("under the hood\n", encoding="utf-8")
    (repo / "page.qmd").write_text("Clean.\n", encoding="utf-8")
    _commit(repo, "txt")
    assert _run(repo, base_ref="all").returncode == 0


@pytest.mark.parametrize("value", ["false", " FALSE ", "False"])
def test_fail_false_downgrades_to_warning(repo: Path, value: str) -> None:
    result = _run(repo, base_ref="all", fail=value)
    assert result.returncode == 0
    assert "::warning file=page.qmd,line=3::banned-idiom:" in result.stdout
    assert "::error" not in result.stdout


@pytest.mark.parametrize("value", ["", "no", "0", "true", "off"])
def test_any_other_fail_value_still_blocks(repo: Path, value: str) -> None:
    assert _run(repo, base_ref="all", fail=value).returncode == 1


def test_idioms_file_replaces_the_list(repo: Path) -> None:
    (repo / "my-idioms.txt").write_text("# mine\nwritten long ago\n", encoding="utf-8")
    _commit(repo, "list")
    result = _run(repo, base_ref="all", idioms_file="my-idioms.txt")
    assert result.returncode == 1
    assert 'banned-idiom: "written long ago"' in result.stdout
    assert "deep dive" not in result.stdout


def test_idioms_file_that_names_nothing_the_page_uses_passes(repo: Path) -> None:
    (repo / "my-idioms.txt").write_text("something unrelated\n", encoding="utf-8")
    _commit(repo, "list")
    assert _run(repo, base_ref="all", idioms_file="my-idioms.txt").returncode == 0


def test_missing_idioms_file_is_an_error_not_a_default(repo: Path) -> None:
    result = _run(repo, base_ref="all", idioms_file="nope.txt")
    assert result.returncode == 1
    assert "does not exist" in result.stdout


def test_empty_idioms_file_fails_the_run(repo: Path) -> None:
    (repo / "empty.txt").write_text("# nothing\n", encoding="utf-8")
    result = _run(repo, base_ref="all", idioms_file="empty.txt")
    assert result.returncode == 1
    assert "lists no phrases" in result.stdout


def test_allow_file_input_reaches_the_script(repo: Path) -> None:
    (repo / "allow.txt").write_text("page.qmd: deep dive\n", encoding="utf-8")
    _commit(repo, "allow")
    assert _run(repo, base_ref="all", allow_file="allow.txt").returncode == 0
    assert _run(repo, base_ref="all", allow_file="missing.txt").returncode == 1


def test_inline_allow_comment_passes_a_whole_run(repo: Path) -> None:
    (repo / "page.qmd").write_text(
        "The old phrase 'deep dive' <!-- prose-allow: deep dive --> stays.\n",
        encoding="utf-8",
    )
    _commit(repo, "allow comment")
    assert _run(repo, base_ref="all").returncode == 0


# ---------------------------------------------------- action and workflow


def _input_names(path: Path, header: str, indent: int) -> set[str]:
    """Input names from a YAML file by line scan (pytest is the only dependency)."""
    names: set[str] = set()
    inside = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line == header:
            inside = True
            continue
        if not inside or not line.strip():
            continue
        depth = len(line) - len(line.lstrip(" "))
        if depth < indent:
            break
        if depth == indent and line.strip().endswith(":"):
            names.add(line.strip()[:-1])
    return names


def test_action_and_workflow_declare_the_same_inputs() -> None:
    action = _input_names(_ACTION_YML, "inputs:", 2)
    workflow = _input_names(_WORKFLOW_YML, "    inputs:", 6)
    assert action == workflow
    assert {"globs", "paths-ignore", "base-ref", "idioms-file", "allow-file", "fail"} <= action


def test_action_defaults_agree_with_the_script() -> None:
    text = _ACTION_YML.read_text(encoding="utf-8")
    assert f"default: '{cqp._DEFAULT_GLOBS}'" in text
    assert "default: 'true'" in text  # fail
    assert cqp._DEFAULT_FAIL is True
