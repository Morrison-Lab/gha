#!/usr/bin/env bash
# Offline tests for scripts/register-self-hosted-runner.sh (gha#1212): the
# per-instance names, directories and work folders, and the @reboot crontab
# line. They use DRY_RUN_CONFIG=1, so nothing is registered or downloaded, and
# a stub `crontab` that keeps its table in a file, so no real crontab is read
# or written.
#
# Usage: bash .github/workflows/scripts/tests/run-register-self-hosted-runner-tests.sh
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"
script="$repo_root/scripts/register-self-hosted-runner.sh"

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir "$work/bin" "$work/home"
cat > "$work/bin/crontab" << 'STUB'
#!/usr/bin/env bash
# Stub: `crontab -l` prints the table (failing when it does not exist yet);
# `crontab -` replaces it with stdin.
table="$STUB_CRONTAB"
case "${1:-}" in
  -l) [ -f "$table" ] && cat "$table" ;;
  -) cat > "$table" ;;
  *) exit 2 ;;
esac
STUB
chmod +x "$work/bin/crontab"

failures=0
cases=0

# check <name> <actual> <expected>
check() {
  cases=$((cases + 1))
  if [[ "$2" != "$3" ]]; then
    echo "::error::$1: expected [$3] but got [$2]"
    failures=$((failures + 1))
  fi
}

# dry <env assignments...>: run the script in dry-run mode on a fresh home.
dry() {
  env -i PATH="$work/bin:$PATH" HOME="$work/home" STUB_CRONTAB="$work/crontab" \
    ORG=Acme DRY_RUN_CONFIG=1 "$@" bash "$script"
}

host=$(hostname -s)
out=$(dry)
check "one instance" "$out" "runner name=private-$host dir=$work/home/actions-runner-private-$host work=/var/tmp/gha-work/private-$host"

out=$(dry RUNNER_INSTANCES=3)
check "three instances: count" "$(wc -l <<< "$out" | tr -d ' ')" "3"
check "three instances: second" "$(sed -n 2p <<< "$out")" "runner name=private-$host-2 dir=$work/home/actions-runner-private-$host-2 work=/var/tmp/gha-work/private-$host-2"
check "three instances: third" "$(sed -n 3p <<< "$out")" "runner name=private-$host-3 dir=$work/home/actions-runner-private-$host-3 work=/var/tmp/gha-work/private-$host-3"

out=$(dry RUNNER_INSTANCES=2 RUNNER_WORK_DIRECTORY=/data/work)
check "explicit work folder: instance 1" "$(sed -n 1p <<< "$out")" "runner name=private-$host dir=$work/home/actions-runner-private-$host work=/data/work"
check "explicit work folder: instance 2 is distinct" "$(sed -n 2p <<< "$out" | sed 's/.* work=//')" "/data/work-2"

if dry RUNNER_INSTANCES=0 > /dev/null 2>&1; then
  check "zero instances is refused" "accepted" "refused"
fi

# No crontab line unless asked.
dry RUNNER_INSTANCES=3 > /dev/null
check "no crontab without INSTALL_REBOOT_CRON" "$([ -f "$work/crontab" ] && echo present || echo absent)" "absent"

# One line, however many times it runs, and other lines are kept.
echo "0 3 * * * echo keep-me" > "$work/crontab"
dry RUNNER_INSTANCES=3 INSTALL_REBOOT_CRON=1 > /dev/null
dry RUNNER_INSTANCES=3 INSTALL_REBOOT_CRON=1 > /dev/null
check "crontab: one @reboot line after two runs" "$(grep -c '^@reboot' "$work/crontab")" "1"
check "crontab: unrelated line kept" "$(grep -c 'keep-me' "$work/crontab")" "1"
check "crontab: line content" "$(grep '^@reboot' "$work/crontab" | sed -e "s| bash .*| bash SCRIPT|" -e 's| PATH=[^ ]*||')" "@reboot ORG=Acme RUNNER_INSTANCES=3 bash SCRIPT"
check "crontab: PATH is carried" "$(grep -c ' PATH=' "$work/crontab")" "1"

# An organization whose name starts with another's keeps its own line.
dry ORG=Acme2 RUNNER_INSTANCES=1 INSTALL_REBOOT_CRON=1 > /dev/null
dry RUNNER_INSTANCES=3 INSTALL_REBOOT_CRON=1 > /dev/null
check "crontab: Acme and Acme2 each keep one line" "$(grep -c '^@reboot' "$work/crontab")" "2"
check "crontab: Acme2 line survives an Acme rerun" "$(grep -c 'ORG=Acme2 ' "$work/crontab")" "1"

# Settings the caller gave are repeated on the line.
dry RUNNER_INSTANCES=3 RUNNER_GROUP=my-group INSTALL_REBOOT_CRON=1 > /dev/null
check "crontab: RUNNER_GROUP is carried" "$(grep -c 'ORG=Acme .*RUNNER_GROUP=my-group ' "$work/crontab")" "1"
check "crontab: unset settings are not added" "$(grep 'ORG=Acme ' "$work/crontab" | grep -c RUNNER_LABELS)" "0"
dry RUNNER_INSTANCES=2 INSTALL_REBOOT_CRON=1 > /dev/null
check "crontab: a rerun with a new count replaces the line" "$(grep '^@reboot ORG=Acme ' "$work/crontab" | sed 's/.*RUNNER_INSTANCES=\([0-9]*\).*/\1/')" "2"
check "crontab: still one Acme line" "$(grep -c '^@reboot ORG=Acme ' "$work/crontab")" "1"

# Starting from no crontab at all.
rm -f "$work/crontab"
dry INSTALL_REBOOT_CRON=1 > /dev/null
check "crontab: created when none existed" "$(grep -c '^@reboot' "$work/crontab")" "1"

# The helpers are called after the script cd-s into the runner directory, so their
# path must be absolute; a relative one fails to find them.
check "helpers: dirname of BASH_SOURCE appears only in SCRIPT_DIR" "$(grep -c 'dirname "${BASH_SOURCE' "$script")" "1"
check "helpers: both are called through SCRIPT_DIR" "$(grep -c '"${SCRIPT_DIR}/' "$script")" "2"

echo "$cases cases, $failures failures"
[[ "$failures" -eq 0 ]]
