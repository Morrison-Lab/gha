- **The remaining `*.yml`-only workflow audits now discover `.yaml` workflows
  too** (#716).
  `run-permissions-docs-tests.py`'s read-only classification, and
  `_selftest.yml`'s `SUBMODULES_TOKEN` and SHA-pin audits, each globbed
  `*.yml` alone, so a `.yaml` workflow bypassed all three silently --- the
  sibling of the job-guard gap fixed in #712.
  The two shell audits move into `audit-workflow-token-usage.sh` and
  `audit-workflow-action-pins.sh`, sharing a `list-workflow-files.sh` that
  fails closed on an empty or missing directory, and each now distinguishes
  `grep`'s "check did not run" status from "found nothing" rather than
  reporting both as clean.
  Both are covered offline by fixtures whose violation lives in a `.yaml`
  file, which this repo's own all-`.yml` tree cannot supply.
