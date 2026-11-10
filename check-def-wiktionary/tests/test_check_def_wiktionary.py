"""Unit tests for check-def-wiktionary, using recorded MediaWiki responses (no network)."""

import importlib.util
import io
import json
from pathlib import Path
from unittest import mock

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("check_def_wiktionary", _DIR / "check-def-wiktionary.py")
assert _spec is not None and _spec.loader is not None
dwk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dwk)

# Shapes of https://en.wiktionary.org/w/api.php?action=query&format=json&titles=...
FOUND = {"batchcomplete": "", "query": {"pages": {"12345": {"pageid": 12345, "ns": 0, "title": "variance"}}}}
MISSING = {"batchcomplete": "", "query": {"pages": {"-1": {"ns": 0, "title": "residual sum of squares", "missing": ""}}}}

ENTRIES = {"variance", "estimator", "residual"}


def lookup(title):
    return title in ENTRIES


def def_text(title, body):
    return f"::: {{#def-x}}\n\n## {title}\n\n{body}\n\n:::".split("\n")


def run(title, body):
    (_, _, t, b), = dwk.def_blocks(def_text(title, body))
    return dwk.check_block(t, b, lookup)


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def fake_response(payload):
    return FakeResponse(json.dumps(payload).encode())


def test_api_lookup_parses_found_and_missing():
    with mock.patch.object(dwk.urllib.request, "urlopen", return_value=fake_response(FOUND)):
        assert dwk.api_lookup("variance") is True
    with mock.patch.object(dwk.urllib.request, "urlopen", return_value=fake_response(MISSING)):
        assert dwk.api_lookup("residual sum of squares") is False


def test_api_lookup_network_error_is_none():
    with mock.patch.object(dwk.urllib.request, "urlopen", side_effect=OSError("blocked")):
        assert dwk.api_lookup("variance") is None


def test_unlinked_term_with_entry_is_flagged():
    msgs = run("Variance", "The **variance** of $X$ is 1.")
    assert len(msgs) == 1 and "en.wiktionary.org/wiki/variance" in msgs[0]


def test_linked_term_passes():
    assert not run("Variance", "The **[variance](https://en.wiktionary.org/wiki/variance)** of $X$ is 1.")
    assert not run("Variance", "The [**variance**](https://en.wiktionary.org/wiki/variance) of $X$ is 1.")


def test_term_without_entry_is_not_flagged():
    assert not run("Residual sum of squares", "The **residual sum of squares** is 1.")


def test_capitalised_title_tries_lowercase_entry():
    assert run("Estimator", "An **Estimator** is a rule.")


def test_only_first_bold_instance_matters():
    body = "The **[variance](https://en.wiktionary.org/wiki/variance)** is 1; the **variance** again."
    assert not run("Variance", body)


def test_link_to_missing_page_is_flagged():
    body = "The **[sum of squares](https://en.wiktionary.org/wiki/sum_of_squares)** is 1."
    msgs = run("Sum of squares", body)
    assert any("does not exist" in m for m in msgs)


def test_allow_comment_exempts():
    assert not run("Variance", "<!-- wiktionary-link: allow -->\nThe **variance** is 1.")


def test_unreachable_lookup_skips_with_note():
    (_, _, t, b), = dwk.def_blocks(def_text("Variance", "The **variance** is 1."))
    msgs = dwk.check_block(t, b, lambda _title: None)
    assert msgs and msgs[0].startswith("::NOTE::")


def test_synonym_title_checks_each_name():
    msgs = run("Variance, estimator", "The **variance** or **estimator** is 1.")
    assert len(msgs) == 2


def test_math_in_title_ignored():
    assert dwk.title_names("Norm $x$, length") == ["Norm", "length"]
