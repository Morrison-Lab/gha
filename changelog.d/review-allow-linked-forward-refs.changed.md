- `claude-code-review` rule 4 now accepts a linked, signposted forward reference when no good reordering exists,
  and flags a PR that removes or unlinks a crossref to hide a forward reference
  (Ezra, 2026-11-19: "when there's no good way to reorder materials to avoid a forward reference, it's better to allow one than to avoid linking at all").
