- `check-term-links`:
  stop treating function words ("and", "not", "that") and the generic nouns "number" and "value" as terms (gha#1488).
  A prerequisite site's logic definitions and `#def-` links made `terms-from` flag every ordinary use of them, 32 times on lds#1859.
  A project still adds its own exclusions through `allow-file`.
