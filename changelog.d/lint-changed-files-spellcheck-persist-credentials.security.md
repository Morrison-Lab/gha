- **`lint-changed-files` and `spellcheck` checkouts now set
  `persist-credentials: false`** (#733).
  Neither job pushes, so the caller's checkout token had no use once the job
  started, but `actions/checkout` persists it into `.git/config` for the
  job's duration by default.
  A consumer migrating from a locally hardened workflow (one that already set
  `persist-credentials: false` everywhere, per its own security sweep) would
  regress on that posture point by adopting the reusable instead.
  #328's hardening sweep predates both files and never covered them.
