- `check-heading-levels` now requires a page's body to start at level 1 (`#`), not level 2, and fails by default (`fail: true`; agents ignore warnings).
  The page title is not a numbered level,
  so a body that starts at `##` numbers its sections 0.1, 0.2 under `number-sections: true`.
  The old rule steered agents toward the numbering bug.
