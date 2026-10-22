#!/usr/bin/env bash
# Register one self-hosted GitHub Actions runner for an organization, on a
# Linux machine (a lab-managed host, or WSL), as the current user with no sudo.
#
# Usage: ORG=<org> bash scripts/register-self-hosted-runner.sh
#
# The workflows that take a `runs-on` input (the check-* and lint-* ones) can
# then target the runner with the label `private-runner`.
#
# Idempotent: if a runner is already configured in $RUNNER_DIR, it only
# starts the runner process when none is running.
#
# Needs the gh CLI logged in as an organization owner (admin:org scope).
# The registration token is minted here and never printed or written to disk.
#
# Safety: the runner joins a runner group that admits PRIVATE repositories
# only, because a pull request from a fork of a public repository can run
# arbitrary code on this machine. The script creates the group if missing and
# refuses to use an existing group that admits public repositories or all
# repositories.
#
# The runner process is started with nohup and does not survive a reboot:
# run this script again after one.
set -euo pipefail

ORG="${ORG:?set ORG to the organization name}"
RUNNER_DIR="${RUNNER_DIR:-$HOME/actions-runner-private}"
RUNNER_NAME="${RUNNER_NAME:-private-$(hostname -s)}"
RUNNER_LABELS="${RUNNER_LABELS:-private-runner,$(hostname -s)}"
RUNNER_GROUP="${RUNNER_GROUP:-private-runners}"

start_runner() {
  cd "$RUNNER_DIR"
  if pgrep -f "$RUNNER_DIR/bin/Runner.Listener" > /dev/null; then
    echo "Runner already running."
    return 0
  fi
  nohup ./run.sh > runner.log 2>&1 &
  echo "Runner started (log: $RUNNER_DIR/runner.log)."
}

if [ -f "$RUNNER_DIR/.runner" ]; then
  echo "Runner already configured in $RUNNER_DIR."
  start_runner
  exit 0
fi

command -v gh > /dev/null || { echo "gh is not installed" >&2; exit 1; }
gh auth status > /dev/null

case "$(uname -m)" in
  x86_64) arch=x64 ;;
  aarch64 | arm64) arch=arm64 ;;
  *) echo "Unsupported architecture: $(uname -m)" >&2; exit 1 ;;
esac

# Mint the token first, so a missing admin:org scope fails before any download
# or group change.
token=$(gh api -X POST "orgs/${ORG}/actions/runners/registration-token" --jq .token)

# The group must admit private repositories only.
group=$(gh api "orgs/${ORG}/actions/runner-groups" --paginate \
  --jq ".runner_groups[] | select(.name == \"${RUNNER_GROUP}\") | @json")
if [ -z "$group" ]; then
  gh api -X POST "orgs/${ORG}/actions/runner-groups" \
    -f name="$RUNNER_GROUP" -f visibility=private > /dev/null
  echo "Created runner group ${RUNNER_GROUP} (private repositories only)."
else
  visibility=$(jq -r .visibility <<< "$group")
  public=$(jq -r .allows_public_repositories <<< "$group")
  if [ "$visibility" = all ] || [ "$public" = true ]; then
    echo "Runner group ${RUNNER_GROUP} admits public repositories; refusing." >&2
    exit 1
  fi
fi

release=$(gh api repos/actions/runner/releases/latest)
version=$(jq -r .tag_name <<< "$release")
version=${version#v}
asset="actions-runner-linux-${arch}-${version}.tar.gz"
# GitHub publishes each tarball's SHA-256 in the release notes.
sha=$(jq -r .body <<< "$release" \
  | grep -F "$asset" | grep -o '[0-9a-f]\{64\}' | head -n 1 || true)
if [ -z "$sha" ]; then
  echo "No SHA-256 for ${asset} in the release notes; refusing to run an unchecked download." >&2
  exit 1
fi

mkdir -p "$RUNNER_DIR"
cd "$RUNNER_DIR"
curl -sSL -o runner.tar.gz \
  "https://github.com/actions/runner/releases/download/v${version}/${asset}"
echo "${sha}  runner.tar.gz" | sha256sum --check --status
tar xzf runner.tar.gz
rm runner.tar.gz

./config.sh --unattended \
  --url "https://github.com/${ORG}" \
  --token "$token" \
  --name "$RUNNER_NAME" \
  --labels "$RUNNER_LABELS" \
  --runnergroup "$RUNNER_GROUP"
unset token

start_runner
