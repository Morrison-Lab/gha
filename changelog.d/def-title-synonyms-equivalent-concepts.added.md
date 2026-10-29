- `check-def-title-synonyms`:
  also warn when a definition title lists two or more names
  and the definition states the term twice,
  with two display equations that each carry a defining operator
  or prose such as "equivalently" (Ezra, 2026-10-29).
  Only true synonyms share a title;
  equivalent but distinct concepts each get their own definition
  and a theorem that they agree.
  `<!-- def-title-synonyms: allow -->` exempts a definition.
  The new rule is a heuristic and warns by default.
