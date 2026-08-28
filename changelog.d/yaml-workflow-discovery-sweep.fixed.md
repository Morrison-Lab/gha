- **The remaining `*.yml`-only workflow audits now discover `.yaml` workflows
  too** (#716).
  `run-permissions-docs-tests.py`'s read-only classification, and
  `_selftest.yml`'s `SUBMODULES_TOKEN` and SHA-pin audits, each globbed
  `*.yml` alone, so a `.yaml` workflow bypassed all three silently --- the
  sibling of the job-guard gap fixed in #712.
  Discovery for the two shell audits moves into a shared
  `list-workflow-files.sh` that covers both extensions, stays top-level only,
  and fails closed on an empty or missing directory, so an audit can no longer
  pass having examined nothing.
