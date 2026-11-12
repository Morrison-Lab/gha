- `check-new-line-breaks` no longer reads punctuation inside an inline HTML tag as prose (gha#1927).
  A dot, `!`, or `?` in an attribute, as in `<img alt="Fig. 1. The model">`, no longer ends a sentence,
  and a `;` in an attribute such as `style="color: red; margin: 0"` no longer counts as a clause break.
  Tag text also no longer counts toward the 80-character length gate, as code spans and URLs already did not.
  A tag follows what Pandoc reads as raw HTML, so `i<p holds. Then q>i` is still prose,
  and so are `<!DOCTYPE ...>` and `<![CDATA[...]]>`.
  An autolink such as `<https://example.com>` is not a tag either.
