- `check-lab-exposition`:
  add a composite action and a reusable workflow, diff-scoped and blocking, that flag a
  definition, result, or remark div that a pull request adds to a lab page,
  or to a file that a lab page includes, and an added include of one.
  A lab applies what the exposition pages teach (Ezra, 2026-11-19).
  A lab page is a file the `pages` pathspecs match (default `*-lab.qmd`),
  and includes are followed transitively.
  `<!-- lab-exposition-ok: reason -->` exempts one item,
  and `whole-tree: true` lists the labs that break the rule.
