- **The `@claude review` matcher no longer fires on a mention quoted as an
  indented code block that opens after a heading or a thematic break**
  (gha#356).
  `strip-non-invoking-markup.sh` only opened an indented code block after a
  blank line, but CommonMark bars an indented block only from *interrupting a
  paragraph* -- after a thematic break, an ATX heading, or a setext-heading
  underline it opens with no blank line at all.
  So a request quoted under a `---` or a `#`/`===` heading rendered as code on
  GitHub yet slipped through the stripper and dispatched a review off quoted
  text -- the same class of false dispatch the code-span and fence handling
  already close.
  A list item is deliberately still not treated as such a predecessor: an
  indented line after one is a list continuation, not code, so stripping it
  would drop a genuine request in the mention gate that shares this script.
