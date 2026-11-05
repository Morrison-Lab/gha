#!/usr/bin/env bash
# Decide whether a self-hosted runner group is safe for private repositories
# only. Reads the group's JSON (from the organization runner-groups API) on
# stdin; exits 0 when the group is safe and 1 when it is not.
#
# Usage: gh api ... | jq -c '.runner_groups[] | ...' | bash scripts/runner-group-is-private.sh
#
# A pull request from a fork of a public repository can run arbitrary code on a
# runner, so the group must keep public repositories out. Two ways do that:
#   - `visibility` is `selected` or `private`, and no public repository is
#     allowed; or
#   - `visibility` is `all` AND `allows_public_repositories` is exactly the
#     boolean `false`. "All" then means every repository in the organization
#     that is not public. GitHub's default group is configured this way.
# Anything else is refused: `allows_public_repositories` true, missing, null or
# not a boolean (a string "false" is not false), or an inherited allowance.
set -euo pipefail

jq -e '
  .allows_public_repositories == false
  and ((.inherited_allows_public_repositories // false) == false)
' > /dev/null
