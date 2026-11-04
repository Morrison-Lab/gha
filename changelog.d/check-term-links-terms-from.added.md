- `check-term-links`:
  add a `terms-from` input (reusable workflow) and a `terms-dirs` input (action) that read prerequisite sites' definitions,
  so a term defined in mds, pds or sds must be linked at its first use in each div of a course site too
  (gha#1462, Ezra, 2026-11-04).
  A private prerequisite repository uses the optional `WORKFLOW_TOKEN` secret.
