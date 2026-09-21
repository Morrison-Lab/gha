Add `checkout-reference-repos` composite action
and `reference-repos` input across `claude-code-review.yml`
and `claude.yml` workflows.
Allows reviewer and coding agents to check out
reference repositories into `.reference-repos/`
with automatic `.git/info/exclude` isolation
so they have direct read access to reference code,
actions, workflows, and guidelines (gha#866).
