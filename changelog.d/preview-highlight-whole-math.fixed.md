- **PR previews no longer show raw TeX where the change highlighter marked
  edited math** (gha#1003).
  `preview/highlight-html-changes.py` wrapped individual changed words in
  `<mark>`, which split an inline expression's `\(` and `\)` delimiters across
  text nodes, so MathJax skipped it (Morrison-Lab/win#98).
  A changed expression inside a `math` span is now marked as a whole, and the
  prose around it is still marked word by word.
