- **New capability: `lint-workflows`** (#330).
  Audits the caller's GitHub Actions workflows and composite actions with
  [`actionlint`](https://github.com/rhysd/actionlint) (syntax/semantics --
  unknown keys, bad `runs-on` labels, invalid `${{ }}` expressions,
  shellcheck over `run:` blocks) and
  [`zizmor`](https://github.com/zizmorcore/zizmor) (security --
  template-injection sinks, credential persistence, overly broad
  permissions, unpinned actions).
  A repo adopting it with a pre-existing backlog of findings can set
  `fail: false` to land as a warn-only baseline and tighten later, rather
  than blocking adoption on a full cleanup up front.
