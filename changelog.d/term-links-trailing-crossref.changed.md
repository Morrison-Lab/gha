- `check-term-links` reports a term followed by a crossref to its definition,
  as in "affine map (@def-affine-map)",
  as `trailing-crossref`, instead of counting it as linked.
  `check-avoided-words` already failed that form under `parenref`.
- `check-avoided-words` gains a warn-only `nounref` rule
  for a definition crossref used as a noun,
  as in `which is @def-affine-map with`,
  which renders as `which is Definition 3 with` (Ezra, 2026-11-23).
