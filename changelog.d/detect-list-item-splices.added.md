- **Detect list-item merge splices in `lint-markdown`** (#324).
  `lint-markdown` gains a `check_list_item_splices.mjs` companion check that flags list items merged directly onto a previous item's continuation line without an intervening blank line, supporting diff-scoping via `base-ref`.

