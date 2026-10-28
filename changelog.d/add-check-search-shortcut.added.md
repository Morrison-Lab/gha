- `check-search-shortcut`:
  add a blocking composite action and reusable workflow that flags a Quarto site
  whose search opens on Ctrl/Cmd-F or Ctrl/Cmd-S
  ([#1287](https://github.com/Morrison-Lab/gha/issues/1287)).
  Quarto's `keyboard-shortcut` defaults to `["f", "/", "s"]` and its script checks no modifier key,
  so the keyup after find-in-page or save opens search.
  The check fails a project that defines a `website:` or `book:` and sets no `keyboard-shortcut`,
  or whose `keyboard-shortcut` lists more than `"/"`.
  It reads the `_quarto*.yml` files whole, with no YAML dependency,
  and `search: false` under `website:` or `book:` is the justified exception.
