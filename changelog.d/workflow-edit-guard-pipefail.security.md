- **`claude-review.yml`, `gemini.yml`, and `claude.yml` fix workflow-edit guard fail-open under pipefail**
  ([#915](https://github.com/Morrison-Lab/gha/issues/915)).
  The inline workflow-edit guard previously piped `printf '%s\n' "$files"`
  into `grep -qE '^\.github/workflows/[^/]+\.ya?ml$'`.
  Under `set -o pipefail`, `grep -q` exits on its first match,
  causing `printf` to fail with `SIGPIPE` (141) on large inputs (>64 KB).
  The pipeline status was promoted to 141,
  making the guard condition evaluate false
  and leaving `REF_ARGS` with `--ref "$PR_BRANCH"`
  so GitHub executed unreviewed workflow YAML from the PR head.
  All four workflow dispatch sites (and example workflows) now use a here-string
  (`grep -qE '^\.github/workflows/[^/]+\.ya?ml$' <<< "$files"`)
  so `grep` is a simple command immune to pipefail SIGPIPE promotion.
  Files are also normalized with `tr -d '\r'`
  to match `detect-pr-workflow-edits.sh` handling for CRLF-terminated file lists.
  Adds offline regression test suite `run-workflow-edit-guard-tests.sh`.
