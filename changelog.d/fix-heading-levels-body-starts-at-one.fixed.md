- `check-heading-levels` now requires a page's body to start at level 1 (`#`), not level 2.
  The page title is not a numbered level,
  so a body that starts at `##` numbers its sections 0.1, 0.2 under `number-sections: true`.
  The old rule steered agents toward the numbering bug.
- **Breaking default:** `check-heading-levels` now fails by default (`fail: true`), since agents ignore warnings.
  A caller that relied on the warn-only default and has pages starting at level 2 turns red on its next PR.
  Set `fail: false` to keep warning only.
