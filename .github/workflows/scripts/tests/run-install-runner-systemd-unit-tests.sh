#!/usr/bin/env bash
# Offline tests for scripts/install-runner-systemd-unit.sh (gha#1543): each
# instance gets a drop-in with ConditionHost for the installing host (or
# RUNNER_HOST), the template unit is copied, each instance is enabled, a missing
# runner directory or a bad host name refuses before anything is written.
#
# Usage: bash .github/workflows/scripts/tests/run-install-runner-systemd-unit-tests.sh
set -uo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"
script="$repo_root/scripts/install-runner-systemd-unit.sh"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
failures=0
fail() { echo "::error::$1"; failures=$((failures + 1)); }

# Stub loginctl and systemctl, logging their arguments.
mkdir -p "$work/bin"
for tool in loginctl systemctl; do
  # shellcheck disable=SC2016 # $* belongs to the stub
  printf '#!/usr/bin/env bash\necho "%s $*" >> "%s/calls"\n' "$tool" "$work" > "$work/bin/$tool"
  chmod +x "$work/bin/$tool"
done
home="$work/home"
for inst in gate-1 gate-2; do
  mkdir -p "$home/actions-runner-private-$inst"
  printf '#!/bin/sh\n' > "$home/actions-runner-private-$inst/run.sh"
  chmod +x "$home/actions-runner-private-$inst/run.sh"
done
run() { env -u RUNNER_HOST HOME="$home" XDG_CONFIG_HOME="$home/.config" PATH="$work/bin:$PATH" "$@" bash "$script" gate-1 gate-2 2>&1; }
units="$home/.config/systemd/user"

out=$(run RUNNER_HOST=cf463-02) || fail "an install should succeed: $out"
[ -f "$units/gha-runner@.service" ] || fail "the template unit should be copied"
grep -q "$repo_root/scripts/run-runner-exclusive.sh" "$units/gha-runner@.service" 2> /dev/null ||
  fail "the unit should start this checkout's run-runner-exclusive.sh"
! grep -q '@GHA_SCRIPTS@' "$units/gha-runner@.service" 2> /dev/null ||
  fail "the unit should carry no unfilled @GHA_SCRIPTS@ placeholder"
for inst in gate-1 gate-2; do
  conf="$units/gha-runner@$inst.service.d/host.conf"
  grep -qx '\[Unit\]' "$conf" 2> /dev/null || fail "$inst's drop-in should open a [Unit] section"
  grep -qx 'ConditionHost=cf463-02' "$conf" 2> /dev/null || fail "$inst's drop-in should pin it to cf463-02"
  grep -qx "systemctl --user enable gha-runner@$inst" "$work/calls" || fail "$inst should be enabled"
done
case "$out" in *"on cf463-02 only"*) ;; *) fail "the summary should name the host: $out" ;; esac

# A rerun on another host moves the instances there, without a second line.
out=$(run RUNNER_HOST=cf463-01) || fail "a rerun should succeed: $out"
[ "$(grep -c '^ConditionHost=' "$units/gha-runner@gate-1.service.d/host.conf")" = 1 ] ||  # phi-allow: a systemd unit name, not an email
  fail "a rerun should replace the host, not add a second one"
grep -qx 'ConditionHost=cf463-01' "$units/gha-runner@gate-1.service.d/host.conf" ||  # phi-allow: a systemd unit name, not an email
  fail "a rerun should pin the instance to the new host"

# The default host is this one.
rm -rf "$units"
out=$(run) || fail "an install without RUNNER_HOST should succeed: $out"
grep -qx "ConditionHost=$(uname -n)" "$units/gha-runner@gate-2.service.d/host.conf" ||  # phi-allow: a systemd unit name, not an email
  fail "the default host should be this host"

# A bad host name refuses before writing anything.
rm -rf "$units"
out=$(run RUNNER_HOST='cf463-02 evil')
[ "$?" = 2 ] || fail "a bad host name should exit 2: $out"
[ ! -e "$units" ] || fail "a bad host name should write nothing"

# A missing runner directory refuses before writing anything.
rm -rf "$home/actions-runner-private-gate-2" "$units"
out=$(run RUNNER_HOST=cf463-02)
[ "$?" = 1 ] || fail "a missing runner should exit 1: $out"
[ ! -e "$units" ] || fail "a missing runner should write nothing"

[ "$failures" = 0 ] && echo "all install-runner-systemd-unit tests passed"
exit "$failures"
