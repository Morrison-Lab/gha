- **The remaining `*.yml`-only workflow audits now discover `.yaml` workflows
  too** (#716).
  `run-permissions-docs-tests.py`'s read-only classification, and
  `_selftest.yml`'s `SUBMODULES_TOKEN` and SHA-pin audits, each globbed
  `*.yml` alone, so a `.yaml` workflow bypassed all three silently --- the
  sibling of the job-guard gap fixed in #712.
  All three now share one `workflow_discovery` module, which fails closed on
  an empty or missing directory rather than handing an audit nothing to
  examine.
- **The SHA-pin audit now sees the `- uses:` list form** (#720).
  It matched workflow text against a line-leading `uses:`, so five action
  references in this repo were exempt purely by how their step was written.
  Both audits moved out of `_selftest.yml` into scripts that walk parsed YAML,
  which sees both spellings and cannot mistake a `uses:` written inside a
  `run:` heredoc for a real reference.
