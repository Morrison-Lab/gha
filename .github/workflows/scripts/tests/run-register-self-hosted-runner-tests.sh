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
check "helpers: all four are called through SCRIPT_DIR" "$(grep -c '"${SCRIPT_DIR}/' "$script")" "4"

# pin-runner-path.sh copies .path into .env (gha#1341).
pin="$repo_root/scripts/pin-runner-path.sh"
rd="$work/runner"
mkdir "$rd"
echo "/opt/quarto/bin:/usr/bin" > "$rd/.path"
printf 'LANG=C.UTF-8' > "$rd/.env"
RUNNER_DIR="$rd" bash "$pin" > /dev/null
check "pin: PATH line added" "$(grep '^PATH=' "$rd/.env")" "PATH=/opt/quarto/bin:/usr/bin"
check "pin: existing line kept on its own line" "$(head -n 1 "$rd/.env")" "LANG=C.UTF-8"
RUNNER_DIR="$rd" bash "$pin" > /dev/null
check "pin: idempotent" "$(grep -c '^PATH=' "$rd/.env")" "1"
printf 'PATH=/custom\n' > "$rd/.env"
RUNNER_DIR="$rd" bash "$pin" > /dev/null
check "pin: a PATH set by hand is kept" "$(cat "$rd/.env")" "PATH=/custom"
rm "$rd/.env"
RUNNER_DIR="$rd" bash "$pin" > /dev/null
check "pin: .env created when missing" "$(cat "$rd/.env")" "PATH=/opt/quarto/bin:/usr/bin"
# pin_fails <name> <.path contents, or "missing">: the pin must exit non-zero,
# say why, and leave .env alone. A blank PATH= line would unset PATH.
pin_fails() {
  rm -f "$rd/.path" "$rd/.env"
  if [ "$2" != missing ]; then printf '%s' "$2" > "$rd/.path"; fi
  echo "LANG=C.UTF-8" > "$rd/.env"
  local err rc=0
  err=$(RUNNER_DIR="$rd" bash "$pin" 2>&1 > /dev/null) || rc=$?
  check "pin: $1 exits non-zero" "$([ "$rc" -ne 0 ] && echo nonzero || echo zero)" "nonzero"
  check "pin: $1 says why" "$err" "No PATH recorded in $rd/.path."
  check "pin: $1 leaves .env alone" "$(cat "$rd/.env")" "LANG=C.UTF-8"
}
nl=$'\n'
pin_fails "missing .path" missing
pin_fails "blank .path" "$nl"
pin_fails "blank first line" "$nl/usr/bin$nl"

# install-runner-cleanup-hook.sh sets the job-completed hook in .env (gha#1352).
hook_installer="$repo_root/scripts/install-runner-cleanup-hook.sh"
prune="$repo_root/scripts/prune-runner-workdir.sh"
printf 'LANG=C.UTF-8' > "$rd/.env"
RUNNER_DIR="$rd" bash "$hook_installer" > /dev/null
check "hook: line added" "$(grep '^ACTIONS_RUNNER_HOOK_JOB_COMPLETED=' "$rd/.env")" "ACTIONS_RUNNER_HOOK_JOB_COMPLETED=$prune"
check "hook: existing line kept on its own line" "$(head -n 1 "$rd/.env")" "LANG=C.UTF-8"
RUNNER_DIR="$rd" bash "$hook_installer" > /dev/null
check "hook: idempotent" "$(grep -c '^ACTIONS_RUNNER_HOOK_JOB_COMPLETED=' "$rd/.env")" "1"
printf 'ACTIONS_RUNNER_HOOK_JOB_COMPLETED=/custom.sh\n' > "$rd/.env"
RUNNER_DIR="$rd" bash "$hook_installer" > /dev/null
check "hook: a hook set by hand is kept" "$(cat "$rd/.env")" "ACTIONS_RUNNER_HOOK_JOB_COMPLETED=/custom.sh"

# prune-runner-workdir.sh, against a stub df whose free space grows by 1 GB for
# each checkout removed: free = STUB_BASE_KB - 1 GB per non-underscore folder.
cat > "$work/bin/df" << 'STUB'
#!/usr/bin/env bash
dir="${@: -1}"
n=$(find "$dir" -mindepth 1 -maxdepth 1 -type d ! -name '_*' | wc -l)
echo "Filesystem 1024-blocks Used Available Capacity Mounted"
echo "stub 0 0 $((STUB_BASE_KB - n * 1048576)) 0% /"
STUB
chmod +x "$work/bin/df"
gb=1048576
# new_work: a work folder with checkouts a (oldest) .. d and the current job's
# checkout cur, plus the runner's own _tool.
new_work() {
  w="$work/gha-work"
  rm -rf "$w"
  mkdir -p "$w/_tool" "$w/cur/cur"
  for r in a b c d; do mkdir -p "$w/$r/$r"; done
  touch -d '3 days ago' "$w/a"; touch -d '2 days ago' "$w/b"
  touch -d '1 day ago' "$w/c"; touch -d '10 days ago' "$w/_tool"
}
# The runner runs a .sh hook as `bash -e -o pipefail`, so the tests do too.
run_prune() {
  env PATH="$work/bin:$PATH" GITHUB_WORKSPACE="$w/cur/cur" "$@" bash --noprofile --norc -e -o pipefail "$prune"
}
left() { find "$w" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort | tr '\n' ' '; }

new_work
touch -d '10 days ago' "$w/a"
run_prune STUB_BASE_KB=$((100 * gb)) > /dev/null
check "prune: a checkout unused for over a week is removed, nothing else" "$(left)" "_tool b c cur d "

new_work
# 5 checkouts + _tool: free starts at 13 - 5 = 8 GB; removing a and b reaches 10.
run_prune STUB_BASE_KB=$((13 * gb)) > /dev/null
check "prune: low space removes the oldest checkouts until 10 GB are free" "$(left)" "_tool c cur d "

new_work
out=$(run_prune STUB_BASE_KB=$((6 * gb)))
check "prune: the current checkout and _tool survive when space stays low" "$(left)" "_tool cur "
check "prune: still-low space is reported" "$(grep -c 'still has under 10 GB' <<< "$out")" "1"

new_work
out=$(env PATH="$work/bin:$PATH" GITHUB_WORKSPACE=relative STUB_BASE_KB=$((6 * gb)) bash -e -o pipefail "$prune"; echo "rc=$?")
check "prune: a malformed workspace removes nothing" "$(left)" "_tool a b c cur d "
check "prune: a malformed workspace warns and exits 0" "$(grep -c '^::warning::.*nothing pruned' <<< "$out") $(tail -n 1 <<< "$out")" "1 rc=0"

new_work
touch -d '10 days ago' "$w/cur"
run_prune STUB_BASE_KB=$((100 * gb)) > /dev/null
check "prune: the current checkout is not aged out" "$(left)" "_tool a b c cur d "
# The 7-day boundary: 6.5 days unused is kept, 7.5 days is removed.
new_work
touch -d '156 hours ago' "$w/a"; touch -d '180 hours ago' "$w/b"
run_prune STUB_BASE_KB=$((100 * gb)) > /dev/null
check "prune: the age boundary is 7 days" "$(left)" "_tool a c cur d "

# A failing df stops pruning with a warning and still exits 0 under -e.
new_work
mv "$work/bin/df" "$work/bin/df.ok"
printf '#!/usr/bin/env bash\nexit 1\n' > "$work/bin/df"
chmod +x "$work/bin/df"
out=$(run_prune STUB_BASE_KB=$((6 * gb)); echo "rc=$?")
mv "$work/bin/df.ok" "$work/bin/df"
check "prune: a failing df removes nothing" "$(left)" "_tool a b c cur d "
check "prune: a failing df warns and exits 0" "$(grep -c 'could not read free space' <<< "$out") $(tail -n 1 <<< "$out")" "1 rc=0"

new_work
out=$(run_prune STUB_BASE_KB=$((100 * gb)) PRUNE_MAX_AGE_DAYS=0)
check "prune: an age of 0 days is refused" "$(left) $(grep -c 'at least 1' <<< "$out")" "_tool a b c cur d  1"

# The mark is what lets a later job of another repository age it correctly.
check "prune: the current checkout is marked as used now" "$(find "$w" -maxdepth 1 -name cur -mmin -5 | wc -l)" "1"

echo "$cases cases, $failures failures"
[[ "$failures" -eq 0 ]]
