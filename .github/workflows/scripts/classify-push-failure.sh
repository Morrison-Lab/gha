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
#   line 1  kind=<workflows-permission|push-protection|non-fast-forward|other>
#   line 2  withhold-patch=<true|false>
#   line 3  headline=<single-line summary, safe for ::error::>
#   line 4  (blank)
#   line 5+ Markdown advice
#
# The advice is Markdown because its other destination is a PR/issue comment.
set -euo pipefail

source_arg="${1:--}"
if [[ "$source_arg" == "-" ]]; then
  log="$(cat)"
else
  log="$(cat "$source_arg")"
fi

# Decided INDEPENDENTLY of `kind`, and deliberately so.
#
# `kind` is a first-match chain, so it answers "what should we tell the
# reader" -- one rejection, one explanation. Whether the commits may be
# published is a different question, and tying it to `kind` made it
# answerable only for the branch that happened to win: a single push that
# both edits a workflow file AND carries a secret matches the
# workflows-permission clause first, and the patch went out with the secret
# in it (gha#361 review round 5).
#
# So the markers are tested on their own, and the caller gates publication on
# this rather than on `kind`. Erring toward withholding costs a re-run;
# publishing a live credential cannot be undone.
withhold_patch=false
if grep -qE 'GH013|GITHUB PUSH PROTECTION|push declined due to repository rule violations|secret scanning' <<<"$log"; then
  withhold_patch=true
fi

# Match the whole "refusing to allow X to create or update workflow" clause
# rather than the trailing scope name. GitHub words the tail differently
# depending on which credential was used: a GitHub App is rejected for
# lacking the "workflows" permission, a Personal Access Token for lacking the
# "workflow" scope. This clause is common to every variant.
#
# Checked before push protection so the more specific explanation wins when
# both match. That ordering is now only about which advice the reader sees --
# it no longer decides whether the patch is published, which is what made it
# a security question before.
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
# The one kind whose caller must NOT publish the patch: these commits carry a
# secret GitHub's scanning caught, so posting them back as a `git am`-able
# patch would republish exactly what the block contained. Actions' own masking
# cannot help -- a scanned secret is commit content, not a configured
# `secrets.*` value (gha#361 review).
#
# The generic rule-violation wording is included deliberately, even though it
# covers rules other than push protection. The asymmetry decides it:
# withholding a patch from an unrelated rule violation costs a re-run, while
# publishing one that carries a live credential cannot be undone.
elif grep -qE 'GH013|GITHUB PUSH PROTECTION|push declined due to repository rule violations|secret scanning' <<<"$log"; then
  kind=push-protection
  headline='Push blocked by a repository rule, possibly a detected secret -- the patch is withheld.'
  advice=$(
    cat <<'EOF'
GitHub refused the push for a repository rule violation. The commonest cause
is secret scanning finding a credential in the commits themselves.

**No patch is included in this comment, deliberately.** If a secret is what
was caught, publishing the commits here would republish it in a public
thread, which is exactly what the block prevented. The run log omits the
patch for the same reason, so the commits exist only on the runner.

To recover: read the rejection below for which rule fired. If it names a
secret, treat that credential as compromised and rotate it, then remove it
from the commits -- not just from the working tree, since a secret in an
earlier commit stays in the history -- and re-run.
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
pushed to the same branch concurrently. Re-running the agent against the
up-to-date branch is the normal recovery; any patch included in this
comment is only needed if the work should be preserved rather than redone.
EOF
  )
else
  kind=other
  # "failed", not "rejected": this branch also covers a push the remote never
  # got to reject -- a DNS failure, a timeout, a bad credential.
  headline="Push failed: the agent's commits could not be pushed."
  advice=$(
    cat <<'EOF'
The push failed for a reason this workflow does not recognize. The raw git
output is included below -- read it first; common causes are an expired or
misscoped token, a branch-protection rule that declines the update, and a
transient network or server error.
EOF
  )
fi

# When the markers fired but a more specific kind won the chain, the chosen
# advice says nothing about a missing patch -- so say it here. Without this
# the reader gets a report whose patch is silently absent, which is the
# contradiction the no-push-attempt and push-protection texts were already
# fixed for.
if [[ "$withhold_patch" == "true" && "$kind" != "push-protection" ]]; then
  advice="$advice"'

**No patch is included in this comment, deliberately.** The rejection also
carries GitHub secret-scanning markers, so the commits may contain a
credential; publishing them here would republish it. Rotate anything the
rejection names, remove it from the commits, and re-run.'
fi

printf 'kind=%s\n' "$kind"
printf 'withhold-patch=%s\n' "$withhold_patch"
printf 'headline=%s\n' "$headline"
printf '\n'
printf '%s\n' "$advice"
