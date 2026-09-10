- **`audit_example_concurrency.py` now examines this repo's own dogfood
  callers, not only the `examples/` stubs** (#821, #854).
  A caller is derived from the `uses:` edge itself:
  any workflow file under `examples/` or `.github/workflows/`
  (`.yml` and `.yaml`, discovered through `workflow_discovery.py`)
  whose job-level `uses:` names one of our reusable workflows
  is audited against that callee's concurrency groups,
  so no list of caller filenames has to be kept in step.
  `website-publish.yml` and the preview family call the same gh-pages
  workflows the stubs do and were subject to the identical deadlock (#809)
  while never being examined.
  The summary line now names both roots and the number of calls found,
  and the audit skips with a notice under a default-branch restore of
  `.github/workflows/` (#598, #765), as the sibling workflow audits do.
  The comparison itself is unchanged; expression-valued groups remain #822.
