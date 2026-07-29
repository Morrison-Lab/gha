#!/usr/bin/env bash
# Classify a failed `git push` from its output, and say what to do about it.
#
# `claude.yml` pushes the agent's commits from a post-step. When that push is
# rejected the commits exist only on the runner, so they die with the job --
# and the raw git error is the only signal a reader gets, buried in a failed
# step of a run log (gha#360). This script turns that output into a named
# failure kind plus advice a human can act on, so the calling composite action
# can emit a real `::error::` and post it back to the thread.
#
# Usage: bash classify-push-failure.sh <push-log-file>
#        bash classify-push-failure.sh -            # read stdin
#
# Output (stdout), in this exact shape so the caller can split it:
#
#   line 1  kind=<workflows-permission|non-fast-forward|other>
#   line 2  headline=<single-line summary, safe for ::error::>
#   line 3  (blank)
#   line 4+ Markdown advice
#
# The advice is Markdown because its other destination is a PR/issue comment.
set -euo pipefail

source_arg="${1:--}"
if [[ "$source_arg" == "-" ]]; then
  log="$(cat)"
else
  log="$(cat "$source_arg")"
fi

# Match the whole "refusing to allow X to create or update workflow" clause
# rather than the trailing scope name. GitHub words the tail differently
# depending on which credential was used -- a GitHub App is rejected `without
# \`workflows\` permission`, a Personal Access Token `without \`workflow\`
# scope` -- while this clause is common to every variant.
if grep -qE 'refusing to allow .* to create or update workflow' <<<"$log"; then
  kind=workflows-permission
  headline='Push rejected: the token cannot write .github/workflows/ -- set the WORKFLOW_TOKEN secret.'
  advice=$(
    cat <<'EOF'
The push was rejected because it touches a file under `.github/workflows/`
and the token used to push cannot write workflow files.

The integrated `GITHUB_TOKEN` never can: GitHub rejects a workflow-file
change made with it, regardless of the `permissions:` block the caller
grants. `claude.yml` resolves its push token as
`secrets.WORKFLOW_TOKEN || secrets.GITHUB_TOKEN`, so this rejection means
`WORKFLOW_TOKEN` is unset in this repository (or lacks the needed scope).

To fix it, add a `WORKFLOW_TOKEN` repository secret -- a classic PAT with
the `repo` and `workflow` scopes, or a GitHub App installation token with
`contents: write` and `workflows: write` -- and pass it through the caller
workflow's `secrets:` block. See the
[Permissions section of the `gha` README](https://github.com/Morrison-Lab/gha#permissions).

Setting a repository secret needs admin access to this repository, so an
`@claude` session cannot do it itself.
EOF
  )
elif grep -qE '\(non-fast-forward\)|\(fetch first\)|Updates were rejected because' <<<"$log"; then
  kind=non-fast-forward
  headline='Push rejected: the branch moved on the remote while this run was working.'
  advice=$(
    cat <<'EOF'
The push was rejected as a non-fast-forward: the branch gained commits on
the remote after this run checked it out. Pushing anyway would discard
them, so the push fails rather than forcing.

This usually means another session, another workflow run, or a person
pushed to the same branch concurrently. Re-running `@claude` on the
up-to-date branch is the normal recovery; the patch below is only needed if
the work should be preserved rather than redone.
EOF
  )
else
  kind=other
  headline="Push rejected: the agent's commits could not be pushed."
  advice=$(
    cat <<'EOF'
The push failed for a reason this workflow does not recognize. The raw git
output is included below -- read it first; common causes are an expired or
misscoped token, a branch-protection rule that declines the update, and a
transient network or server error.
EOF
  )
fi

printf 'kind=%s\n' "$kind"
printf 'headline=%s\n' "$headline"
printf '\n'
printf '%s\n' "$advice"
