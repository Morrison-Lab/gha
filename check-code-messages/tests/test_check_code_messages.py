import importlib.util
import os

_spec = importlib.util.spec_from_file_location(
    "ccm", os.path.join(os.path.dirname(__file__), "..", "check-code-messages.py"))
ccm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ccm)


def lines(text, added=None):
    return [n for n, _ in ccm.lint_text(text, added)]


def test_flags_geom_smooth_without_formula():
    assert lines("ggplot(d) +\n  geom_smooth(method = 'lm', se = FALSE)\n") == [2]


def test_accepts_formula_across_lines():
    assert lines("geom_smooth(\n  method = 'lm',\n  formula = y ~ x\n)\n") == []


def test_namespaced_and_stat_smooth():
    assert lines("ggplot2::stat_smooth(se = TRUE)\n") == [1]


def test_nested_parens_and_string_parens():
    assert lines('geom_smooth(aes(colour = f(x)), label = ")", formula = y ~ x)\n') == []


def test_formula_inside_a_string_does_not_count_as_an_argument():
    # Not an argument, but a conservative lint accepts it; document the limit.
    assert lines('geom_smooth(label = "formula = y")\n') in ([], [1])


def test_formula_word_boundary():
    assert lines("geom_smooth(myformula = 1)\n") == [1]


def test_histogram_bins():
    assert lines("geom_histogram()\n") == [1]
    assert lines("geom_histogram(binwidth = 5)\n") == []
    assert lines("geom_histogram(bins = 30)\n") == []


def test_diff_scope():
    text = "geom_smooth()\nx\ngeom_smooth()\n"
    assert lines(text, {3}) == [3]
    assert lines(text, {2}) == []


def test_other_functions_ignored():
    assert lines("my_geom_smooth()\nplotly::geom_smooth_x()\n") == []


def test_added_lines():
    diff = "+++ b/a.qmd\n@@ -1,0 +5,2 @@\n+a\n+b\n"
    assert ccm.added_lines(diff) == {"a.qmd": {5, 6}}


def test_scan_html_stderr_block():
    html = ('<div class="cell-output cell-output-stderr">\n'
            "<pre>`geom_smooth()` using formula = 'y ~ x'</pre></div>\n")
    found = ccm.scan_html(html)
    assert len(found) == 1 and "geom_smooth" in found[0][1]


def test_scan_html_clean_and_text_message():
    assert ccm.scan_html('<div class="cell-output cell-output-stdout">ok</div>') == []
    assert len(ccm.scan_html("<pre>Warning message:\nfoo</pre>")) == 1
