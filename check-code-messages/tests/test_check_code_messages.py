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
    call = 'geom_smooth(aes(colour = f(x)), label = ")", method = "lm", formula = y ~ x)\n'
    assert lines(call) == []


def test_method_is_needed_too():
    assert lines("geom_smooth(formula = y ~ x)\n") == [1]
    assert lines("geom_smooth(method = 'lm')\n") == [1]


def test_commented_out_or_quoted_arguments_do_not_count():
    assert lines("geom_smooth(method = 'lm', # formula = y ~ x\n  se = FALSE)\n") == [1]
    assert lines('geom_smooth(method = "lm", label = "formula = y")\n') == [1]


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


def test_code_only_masks_prose_and_other_languages():
    text = "Use `geom_smooth()` here.\n```{python}\ngeom_smooth()\n```\n```{r}\ngeom_smooth()\n```\n"
    masked = ccm.code_only(text)
    assert lines(masked) == [6]
    assert masked.count("\n") == text.count("\n")


def test_code_only_handles_tildes_and_plain_r_fence():
    assert lines(ccm.code_only("~~~r\ngeom_smooth()\n~~~\n")) == [2]
    assert lines(ccm.code_only("```\ngeom_smooth()\n```\n")) == []


def test_code_only_accepts_pandoc_class_fence():
    assert lines(ccm.code_only("```{.r}\ngeom_smooth()\n```\n")) == [2]


def test_rendered_prose_warning_message_not_flagged():
    assert ccm.scan_html("<p>R prints Warning message: in the console.</p>") == []


def test_added_lines():
    diff = "+++ b/a.qmd\n@@ -1,0 +5,2 @@\n+a\n+b\n"
    assert ccm.added_lines(diff) == {"a.qmd": {5, 6}}


def test_scan_html_stderr_block():
    html = ('<div class="cell-output cell-output-stderr">\n'
            "<pre>`geom_smooth()` using formula = 'y ~ x'</pre></div>\n")
    found = ccm.scan_html(html)
    assert len(found) == 1 and "geom_smooth" in found[0][1]


def test_scan_html_multiline_block_reported_once_with_text():
    html = ('<div class="cell-output cell-output-stderr">\n<pre><code>\n'
            "`geom_smooth()` using formula = 'y ~ x'\n</code></pre></div>\n")
    found = ccm.scan_html(html)
    assert len(found) == 1 and "geom_smooth" in found[0][1]


def test_scan_html_clean_and_text_message():
    assert ccm.scan_html('<div class="cell-output cell-output-stdout">ok</div>') == []
    assert len(ccm.scan_html("<pre>`stat_bin()` using `bins = 30`.</pre>")) == 1
