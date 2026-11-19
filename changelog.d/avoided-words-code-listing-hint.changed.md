- `check-avoided-words` now says how to fix a position word that points at code,
  such as "the code below" or "the chunk above": <!-- check-avoided-words: allow -->
  label the chunk as a Quarto listing (`lst-label` and `lst-cap`, or a `::: {#lst-...}` div around a language tabset)
  and cite it with `@lst-`
  ([lds#2847](https://github.com/Morrison-Lab/lds/issues/2847)).
  What the check flags is unchanged.
