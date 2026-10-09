- **`preview`: change highlighting no longer breaks math in the preview**
  ([#1003](https://github.com/Morrison-Lab/gha/issues/1003)).
  The diff is word by word, so a change inside an expression such as
  `\(x + y\)` used to put the mark around the changed word only.
  That split the expression across text nodes, and MathJax, which matches a
  delimiter pair only within one run of text, left it as raw TeX.
  A math element (any element with class `math`, as Pandoc writes
  `span.math` and `div.math`) that overlaps a change now gets one mark
  around its whole content, placed inside the element.
  A `\(...\)`, `\[...\]` or `$$...$$` expression in other text is either
  wholly inside one mark or outside every mark.
  Checked in headless Chromium with MathJax 3: the pre-fix highlighter left
  24 runs of raw TeX on a six-paragraph test page, and the fixed one leaves
  none.
