#!/usr/bin/env bash
# check-one-function-per-file: allow-multiple
# Register one self-hosted GitHub Actions runner for an organization, on a
# Linux machine (a lab-managed host, or WSL), as the current user with no sudo.
#
# Usage: ORG=<org> bash scripts/register-self-hosted-runner.sh
#
# The workflows that take a `runs-on` input (the check-* and lint-* ones) can
# then target the runner with the label `private-runner`.
#
# Idempotent: if a runner is already configured in $RUNNER_DIR, it checks the
# runner group again and only starts the runner process when none is running.
#
# Needs the gh CLI logged in as an organization owner (admin:org scope), and
# jq. Creating a runner group needs the GitHub Team plan or higher.
# The registration token is minted here, passed to the runner through its
# environment (not its command line, which other users of the host can read),
# and never printed or written to disk.
#
# Safety: the runner joins a runner group that admits PRIVATE repositories
# only, because a pull request from a fork of a public repository can run
# arbitrary code on this machine. The script creates the group if missing and
# refuses to use an existing group whose visibility is `all`, or that admits
# public repositories.
#
# RUNNER_INSTANCES=<n> (default 1) sets up n runners, so n jobs run at once on
# the host. Instance 1 uses RUNNER_DIR and RUNNER_NAME as above; instance k > 1
# uses "<RUNNER_DIR>-k" and "<RUNNER_NAME>-k", with the same labels and group.
# Each is a separate runner, with its own directory, work folder and process.
# Raising n later adds the new instances and leaves the existing ones alone.
#
# The runner process is started with nohup and does not survive a reboot:
# run this script again after one.
# If a runner with the same name is already registered, configuration fails:
# remove the old one in the organization's runner settings first.
set -euo pipefail

ORG="${ORG:?set ORG to the organization name}"
RUNNER_DIR="$(realpath -m "${RUNNER_DIR:-$HOME/actions-runner-private}")"
RUNNER_NAME="${RUNNER_NAME:-private-$(hostname -s)}"
RUNNER_LABELS="${RUNNER_LABELS:-private-runner,$(hostname -s)}"
RUNNER_GROUP="${RUNNER_GROUP:-private-runners}"

RUNNER_INSTANCES="${RUNNER_INSTANCES:-1}"
case "$RUNNER_INSTANCES" in
  '' | *[!0-9]* | 0) echo "RUNNER_INSTANCES must be a positive integer." >&2; exit 1 ;;
esac
if [ "$RUNNER_INSTANCES" -gt 1 ]; then
  # Run this script once per instance, so each keeps the single-runner flow.
  for ((k = 1; k <= RUNNER_INSTANCES; k++)); do
    if [ "$k" -eq 1 ]; then
      RUNNER_INSTANCES=1 bash "${BASH_SOURCE[0]}"
    else
      RUNNER_INSTANCES=1 RUNNER_DIR="${RUNNER_DIR}-${k}" RUNNER_NAME="${RUNNER_NAME}-${k}" bash "${BASH_SOURCE[0]}"
    fi
  done
  exit 0
fi

for tool in gh jq; do
  command -v "$tool" > /dev/null || { echo "$tool is not installed" >&2; exit 1; }
done
gh auth status > /dev/null

start_runner() {
  RUNNER_DIR="$RUNNER_DIR" bash "$(dirname "${BASH_SOURCE[0]}")/seed-runner-python-toolcache.sh" ||
    echo "warning: Python toolcache seeding failed; Python-based checks may fail" >&2
  cd "$RUNNER_DIR"
  # The listener's command line holds the physical path.
  physical_dir=$(pwd -P)
  if pgrep -f "${physical_dir}/(run.sh|bin/Runner.Listener)" > /dev/null; then
    echo "Runner already running."
    return 0
  fi
  nohup ./run.sh > runner.log 2>&1 &
  echo "Runner started (log: $RUNNER_DIR/runner.log)."
}

# Print the runner group's JSON, or nothing when it does not exist.
find_group() {
  gh api "orgs/${ORG}/actions/runner-groups" --paginate \
    | jq -c --arg name "$RUNNER_GROUP" '.runner_groups[] | select(.name == $name)' \
    | head -n 1
}

# Refuse a group that admits all repositories or any public repository.
refuse_unless_private() {
  local group=$1
  local visibility public inherited
  visibility=$(jq -r .visibility <<< "$group")
  public=$(jq -r .allows_public_repositories <<< "$group")
  inherited=$(jq -r '.inherited_allows_public_repositories // false' <<< "$group")
  if [ "$visibility" = all ] || [ "$public" = true ] || [ "$inherited" = true ]; then
    echo "Runner group ${RUNNER_GROUP} admits all or public repositories; refusing." >&2
    exit 1
  fi
}

if [ -f "$RUNNER_DIR/.runner" ]; then
  echo "Runner already configured in $RUNNER_DIR."
  group=$(find_group)
  if [ -z "$group" ]; then
    echo "Runner group ${RUNNER_GROUP} does not exist; refusing to start the runner." >&2
    exit 1
  fi
  refuse_unless_private "$group"
  start_runner
  exit 0
fi

case "$(uname -m)" in
  x86_64) arch=x64 ;;
  aarch64 | arm64) arch=arm64 ;;
  *) echo "Unsupported architecture: $(uname -m)" >&2; exit 1 ;;
esac

# Mint the token first, so a missing admin:org scope fails before any download
# or group change.
token=$(gh api -X POST "orgs/${ORG}/actions/runners/registration-token" --jq .token)

group=$(find_group)
if [ -z "$group" ]; then
  gh api -X POST "orgs/${ORG}/actions/runner-groups" \
    -f name="$RUNNER_GROUP" -f visibility=private > /dev/null
  echo "Created runner group ${RUNNER_GROUP} (private repositories only)."
else
  refuse_unless_private "$group"
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
curl -sSLf -o runner.tar.gz \
  "https://github.com/actions/runner/releases/download/v${version}/${asset}"
if ! echo "${sha}  runner.tar.gz" | sha256sum --check --status; then
  echo "SHA-256 mismatch for ${asset}; refusing to run it." >&2
  rm -f runner.tar.gz
  exit 1
fi
tar xzf runner.tar.gz
rm runner.tar.gz

# The runner reads the token from this variable and removes it from its
# environment, so it never appears in the process list.
ACTIONS_RUNNER_INPUT_TOKEN="$token" ./config.sh --unattended \
  --url "https://github.com/${ORG}" \
  --name "$RUNNER_NAME" \
  --labels "$RUNNER_LABELS" \
  --runnergroup "$RUNNER_GROUP"
unset token

start_runner
