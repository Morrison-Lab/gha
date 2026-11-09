#!/usr/bin/env bash
# Offline tests for scripts/sample-runner-load.sh (gha#1736): one line per sample
# with load, memory, swap and the biggest processes, rotation past the size cap,
# and a warning for a bad cap.
#
# Usage: bash .github/workflows/scripts/tests/run-sample-runner-load-tests.sh
set -uo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"
script="$repo_root/scripts/sample-runner-load.sh"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
failures=0
fail() { echo "::error::$1"; failures=$((failures + 1)); }

printf '103.5 98.2 60.1 5/900 12345\n' > "$work/loadavg"
printf '%s\n' 'MemTotal:       16777216 kB' 'MemAvailable:    2097152 kB' \
  'SwapTotal:       4194304 kB' 'SwapFree:               0 kB' > "$work/meminfo"
printf '%s\n' '3145728 Runner.Worker' '2097152 dotnet' '1048576 Rscript' '512000 quarto' > "$work/ps"
export SAMPLE_LOADAVG="$work/loadavg" SAMPLE_MEMINFO="$work/meminfo" SAMPLE_PS="$work/ps"

# One sample is one line carrying every field.
log="$work/a.log"
SAMPLE_LOG="$log" SAMPLE_TOP=3 bash "$script" || fail "a sample should not fail"
[ "$(wc -l < "$log")" = 1 ] || fail "one sample should write one line: $(cat "$log")"
line=$(cat "$log")
case "$line" in *"load=103.5 98.2 60.1 "*) ;; *) fail "the line should carry the three load averages: $line" ;; esac
case "$line" in *"mem_avail_mb=2048 "*) ;; *) fail "the line should carry available memory in MB: $line" ;; esac
case "$line" in *"swap_used_mb=4096 "*) ;; *) fail "the line should carry swap used in MB: $line" ;; esac
case "$line" in *"top=Runner.Worker:3072,dotnet:2048,Rscript:1024") ;; *) fail "the line should end with the top 3 processes: $line" ;; esac

# A second sample appends.
SAMPLE_LOG="$log" SAMPLE_TOP=3 bash "$script" || fail "a second sample should not fail"
[ "$(wc -l < "$log")" = 2 ] || fail "a second sample should append a line"

# Past the size cap the log moves to .1 and a new log starts.
rm -f "$work/b.log" "$work/b.log.1"
head -c 3000 /dev/zero | tr '\0' 'x' > "$work/b.log"
SAMPLE_LOG="$work/b.log" SAMPLE_MAX_KB=1 bash "$script" || fail "rotation should not fail"
[ -s "$work/b.log.1" ] || fail "a full log should be moved to .1"
[ "$(wc -l < "$work/b.log")" = 1 ] || fail "the new log should hold one line after rotation"

# A bad cap warns and still samples.
rm -f "$work/c.log"
out=$(SAMPLE_LOG="$work/c.log" SAMPLE_MAX_KB=abc bash "$script" 2>&1) || fail "a bad cap should not fail"
case "$out" in *'::warning::'*) ;; *) fail "a bad cap should warn: $out" ;; esac
[ -s "$work/c.log" ] || fail "a bad cap should still write a sample"

[ "$failures" = 0 ] && echo "all sample-runner-load tests passed"
exit "$failures"
