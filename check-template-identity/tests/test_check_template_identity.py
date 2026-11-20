"""Tests for check-template-identity."""

import importlib.util
import os
import re
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, os.pardir, os.pardir)
SCRIPT = os.path.join(HERE, os.pardir, "check-template-identity.py")
spec = importlib.util.spec_from_file_location("check_template_identity", SCRIPT)
cti = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cti)

# Built from parts, so no scanner reads these fixtures as real links.
TEMPLATE = "Acme-Lab/tpl"
REPO_URL = "github.com/" + TEMPLATE
PAGES_URL = "acme-lab.github.io/tpl"
NEEDLES = cti.forbidden_strings(TEMPLATE, ["Template Title"])


def found(line):
    return cti.find_in_line(line, NEEDLES)


def test_needles_are_derived_and_lower_cased():
    assert NEEDLES == [REPO_URL.lower(), PAGES_URL, "template title"]


@pytest.mark.parametrize("line", [
    "repo-url: https://" + REPO_URL,
    "site-url: https://" + PAGES_URL + "/",
    "URL: https://" + REPO_URL.upper() + ", https://example.org",
    'title: "Template Title"',
    "href: https://" + REPO_URL + "/issues",
    "See https://" + REPO_URL + ".",
    "See https://" + REPO_URL + ". Then edit it.",
    "git clone https://" + REPO_URL + ".git",
    "git clone https://" + REPO_URL + ".git.",
])
def test_template_identity_is_found(line):
    assert len(found(line)) == 1


@pytest.mark.parametrize("line", [
    "repo-url: https://github.com/Acme-Lab/my-site",
    "repo-url: https://" + REPO_URL + "-fork",
    "repo-url: https://" + REPO_URL + "2",
    "repo-url: https://" + REPO_URL + ".v2",
    "site-url: https://" + PAGES_URL + ".v2/",
    "git clone https://" + REPO_URL + ".github.git",
    "git clone https://" + REPO_URL + ".git2",
    "site-url: https://my-" + PAGES_URL,
    "title: Template Titles",
    "title: My site",
    "href: https://" + REPO_URL + "  # check-template-identity: allow: credit link",
])
def test_other_values_pass(line):
    assert found(line) == []


def test_allow_comment_needs_a_reason():
    assert len(found("href: https://" + REPO_URL + "  # check-template-identity: allow:")) == 1


def test_a_longer_name_does_not_hide_a_later_match():
    assert len(found("https://%s-fork and https://%s" % (REPO_URL, REPO_URL))) == 1


def run_main(tmp_path, files, **env):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    full = {k: v for k, v in os.environ.items() if not k.startswith(("CTI_", "GITHUB_"))}
    full.update({"CTI_TEMPLATE": TEMPLATE, "CTI_REPOSITORY": "Acme-Lab/my-site"})
    full.update(env)
    return subprocess.run(["python3", SCRIPT], cwd=tmp_path, env=full,
                          capture_output=True, text=True)


STALE = {"_quarto.yml": "website:\n  repo-url: https://%s\n" % REPO_URL}


def test_main_fails_on_a_stale_value_and_names_its_line(tmp_path):
    result = run_main(tmp_path, STALE)
    assert result.returncode == 1
    assert "::error file=_quarto.yml,line=2," in result.stdout
    assert "examined 1 file(s), 1 finding(s)" in result.stdout


def test_main_warns_only_when_fail_is_false(tmp_path):
    result = run_main(tmp_path, STALE, CTI_FAIL="false")
    assert result.returncode == 0 and "::warning file=_quarto.yml" in result.stdout


def test_main_passes_a_site_with_its_own_values(tmp_path):
    result = run_main(tmp_path, {"_quarto.yml": "website:\n  title: Mine\n"})
    assert result.returncode == 0 and "0 finding(s)" in result.stdout


def test_main_skips_in_the_template_itself(tmp_path):
    result = run_main(tmp_path, STALE, CTI_REPOSITORY=TEMPLATE.lower())
    assert result.returncode == 0 and "nothing to check" in result.stdout


def test_main_reads_the_repository_from_github(tmp_path):
    result = run_main(tmp_path, STALE, CTI_REPOSITORY="", GITHUB_REPOSITORY=TEMPLATE)
    assert result.returncode == 0 and "nothing to check" in result.stdout


def test_main_errors_when_no_file_matches_even_warn_only(tmp_path):
    result = run_main(tmp_path, {"other.txt": "x\n"}, CTI_FAIL="false")
    assert result.returncode == 2 and "read nothing" in result.stdout


def test_scan_stops_when_a_file_cannot_be_read(tmp_path):
    with pytest.raises(SystemExit, match="cannot read"):
        cti.scan([str(tmp_path / "gone.yml")], NEEDLES)


def test_main_reads_files_and_strings_from_the_environment(tmp_path):
    result = run_main(tmp_path, {"site.yml": "title: Other Title\n"},
                      CTI_FILES="site.yml", CTI_STRINGS="First\nOther Title\n")
    assert result.returncode == 1 and "'other title'" in result.stdout


@pytest.mark.parametrize("bad", ["", "no-slash", "a/b/c"])
def test_main_rejects_a_malformed_template(tmp_path, bad):
    assert run_main(tmp_path, STALE, CTI_TEMPLATE=bad).returncode == 2


def _declared_default(path, key):
    text = open(os.path.join(ROOT, path), encoding="utf-8").read()
    block = re.search(r"^ {2,6}%s:\n(.*?)(?=^ {2,6}[\w-]+:\n|\Z)" % key, text, re.S | re.M)
    assert block, "%s declares no %s input" % (path, key)
    return re.search(r"default: (.*)", block.group(1)).group(1).strip().strip("'")


@pytest.mark.parametrize("path", [
    "check-template-identity/action.yml",
    ".github/workflows/check-template-identity.yml",
])
def test_declared_defaults_agree_with_the_script(path):
    assert _declared_default(path, "files") == cti.DEFAULT_FILES
    assert _declared_default(path, "fail") == "true"
