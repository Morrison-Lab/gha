- **`audit_callee_permissions.py` judges a new job against the union of the
  base jobs' grants** rather than reporting any new job that requests
  permissions.
  Callers already grant every base job's permissions, so a reusable
  workflow split into two jobs within that union breaks no caller.
  A new job is still reported when it asks for more, or when a base job
  inherits the caller's whole grant and the union is unknown.
  This is what lets `update-snapshots` move its push into a separate job
  (Morrison-Lab/bcs#1110).
