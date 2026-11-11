- `audit_callee_permissions.py` now lets an existing job of a reusable workflow take a permission that another of its jobs already requests, up to that job's level.
  Every working caller already grants such a key, so no caller needs a new grant.
  New jobs were already judged this way.
  This lets `require-clean-verdict` read PR comments with the `pull-requests: read` that `find-fallback-verdict` already holds ([gha#1365](https://github.com/Morrison-Lab/gha/issues/1365)).
