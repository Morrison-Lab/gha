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
# The default RUNNER_DIR is "~/actions-runner-private-<host>"; an existing runner
# in the old default, "~/actions-runner-private", with this host's name is kept.
# Each is a separate runner, with its own directory, work folder and process.
# Raising n later adds the new instances and leaves the existing ones alone.
#
# RUNNER_WORK_DIRECTORY (default /var/tmp/gha-work/<runner name>) is the local
# folder the runner checks out into; see the comment where it is set.
#
# The runner process is started with nohup and does not survive a reboot:
# run this script again after one, or run it once with INSTALL_REBOOT_CRON=1 to
# add an @reboot crontab line that does so (one line, replaced on a rerun).
# DRY_RUN_CONFIG=1 prints the names and directories a run would use and exits.
# If a runner with the same name is already registered, configuration fails:
# remove the old one in the organization's runner settings first.
set -euo pipefail

ORG="${ORG:?set ORG to the organization name}"
RUNNER_NAME="${RUNNER_NAME:-private-$(hostname -s)}"
# The default directory carries the host name, so two hosts that share a home
# directory (NFS) do not share a runner. A runner an earlier version of this
# script configured in the old default directory keeps working there.
if [ -z "${RUNNER_DIR:-}" ] && [ -f "$HOME/actions-runner-private/.runner" ] &&
  [ "$(jq -r .agentName "$HOME/actions-runner-private/.runner")" = "$RUNNER_NAME" ]; then
  RUNNER_DIR="$HOME/actions-runner-private"
fi
RUNNER_DIR="$(realpath -m "${RUNNER_DIR:-$HOME/actions-runner-private-$(hostname -s)}")"
RUNNER_LABELS="${RUNNER_LABELS:-private-runner,$(hostname -s)}"
RUNNER_GROUP="${RUNNER_GROUP:-private-runners}"
# The work folder (checkouts, renders) is on local disk, not in RUNNER_DIR:
# RUNNER_DIR is on the NFS home, where a shallow clone took 10 s against 0.6 s
# locally and creating 5000 files 8 s against 0.1 s (cf463-02, 2026-10-23).
# /var/tmp, not /tmp, because /tmp is cleared at boot. It takes effect when a
# runner is configured; an already-configured runner keeps its work folder.
RUNNER_WORK_DIRECTORY="${RUNNER_WORK_DIRECTORY:-/var/tmp/gha-work/$RUNNER_NAME}"

# With INSTALL_REBOOT_CRON=1, put one @reboot line in the user's crontab that
# runs this script again with the same ORG and RUNNER_INSTANCES, so the
# runners come back after a reboot (an already-configured runner is only
# started). The line is tagged, so running this again replaces it instead of
# adding a second. Other crontab lines are left alone.
install_reboot_cron() {
  [ "${INSTALL_REBOOT_CRON:-}" = 1 ] || return 0
  local tag="# gha-self-hosted-runners ${ORG}"
  local script line current
  script=$(realpath "${BASH_SOURCE[0]}")
  line="@reboot ORG=${ORG} RUNNER_INSTANCES=${RUNNER_INSTANCES} bash ${script} ${tag}"
  # `crontab -l` fails when there is no crontab yet; that is an empty one.
  current=$(crontab -l 2> /dev/null || true)
  { grep -vF "$tag" <<< "$current" || true; echo "$line"; } | crontab -
  echo "Installed the @reboot crontab line (${tag})."
}

RUNNER_INSTANCES="${RUNNER_INSTANCES:-1}"
case "$RUNNER_INSTANCES" in
  '' | *[!0-9]* | 0) echo "RUNNER_INSTANCES must be a positive integer." >&2; exit 1 ;;
esac
if [ "$RUNNER_INSTANCES" -gt 1 ]; then
  # Run this script once per instance, so each keeps the single-runner flow.
  for ((k = 1; k <= RUNNER_INSTANCES; k++)); do
    if [ "$k" -eq 1 ]; then
      INSTALL_REBOOT_CRON=0 RUNNER_INSTANCES=1 bash "${BASH_SOURCE[0]}"
    else
      INSTALL_REBOOT_CRON=0 RUNNER_INSTANCES=1 RUNNER_DIR="${RUNNER_DIR}-${k}" \
        RUNNER_NAME="${RUNNER_NAME}-${k}" \
        RUNNER_WORK_DIRECTORY="${RUNNER_WORK_DIRECTORY}-${k}" bash "${BASH_SOURCE[0]}"
    fi
  done
  install_reboot_cron
  exit 0
fi

# DRY_RUN_CONFIG=1 prints what this run would use and touches nothing else
# (with INSTALL_REBOOT_CRON=1 it still writes the crontab line).
if [ "${DRY_RUN_CONFIG:-}" = 1 ]; then
  echo "runner name=${RUNNER_NAME} dir=${RUNNER_DIR} work=${RUNNER_WORK_DIRECTORY}"
  install_reboot_cron
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
  install_reboot_cron
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
  --runnergroup "$RUNNER_GROUP" \
  --work "$RUNNER_WORK_DIRECTORY"
unset token

start_runner
install_reboot_cron
