#!/usr/bin/env bash
# Offline tests for scripts/check-preinstalled-apt-packages.sh (gha#1758): a
# package dpkg lists passes, a missing tool package fails naming the runner and
# the package, a missing library only warns, a missing tool whose command is on
# PATH passes, a missing tool under a cluster render only warns, and an empty
# list passes.
#
# Usage: bash .github/workflows/scripts/tests/run-check-preinstalled-apt-packages-tests.sh
set -uo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"
script="$repo_root/scripts/check-preinstalled-apt-packages.sh"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
failures=0
fail() { echo "::error::$1"; failures=$((failures + 1)); }

# A fake dpkg that knows only the packages in $work/installed, on a PATH that
# holds only the tools the script needs, so a real rsvg-convert on this host
# cannot satisfy a case meant to miss it.
mkdir -p "$work/bin" "$work/sys" "$work/tools"
# shellcheck disable=SC2016 # $2 belongs to the fake dpkg
printf '#!/usr/bin/env bash\ngrep -qx "$2" "%s/installed"\n' "$work" > "$work/bin/dpkg"
chmod +x "$work/bin/dpkg"
for tool in bash grep hostname; do ln -s "$(command -v "$tool")" "$work/sys/$tool"; done
printf '%s\n' git-man > "$work/installed"
base_path="$work/bin:$work/sys"

run() { env PATH="$1" RUNNER_NAME=private-test-1 APT_PACKAGES="$2" CLUSTER_RENDER="${3:-}" bash "$script" 2>&1; }

out=$(run "$base_path" "git-man") || fail "a package dpkg lists should pass: $out"

out=$(run "$base_path" "git-man librsvg2-bin poppler-utils libfoo-dev")
status=$?
[ "$status" = 1 ] || fail "a missing tool package should fail, got $status: $out"
case "$out" in *"::error::Runner private-test-1 "*) ;; *) fail "the error should name the runner: $out" ;; esac
case "$out" in *"lacks librsvg2-bin poppler-utils,"*) ;; *) fail "the error should list both missing tools: $out" ;; esac
case "$out" in *"::error::"*git-man*) fail "the error should not list a present package: $out" ;; esac
case "$out" in *"::error::"*libfoo-dev*) fail "the error should not list a non-tool package: $out" ;; esac
case "$out" in *"::warning::"*libfoo-dev*) ;; *) fail "a missing non-tool package should warn: $out" ;; esac

out=$(run "$base_path" "libfoo-dev libnode109") || fail "missing non-tool packages alone should only warn: $out"

printf '#!/bin/sh\n' > "$work/tools/rsvg-convert"
chmod +x "$work/tools/rsvg-convert"
out=$(run "$work/tools:$base_path" "librsvg2-bin") ||
  fail "a package whose command is on PATH should pass: $out"
case "$out" in *"$work/tools/rsvg-convert"*) ;; *) fail "the pass should say where the command is: $out" ;; esac

out=$(run "$base_path" "librsvg2-bin" true) || fail "a cluster render should only warn: $out"
case "$out" in *"::warning::"*librsvg2-bin*) ;; *) fail "a cluster render should warn naming the tool: $out" ;; esac

out=$(run "$base_path" "") || fail "an empty list should pass: $out"

[ "$failures" = 0 ] && echo "all check-preinstalled-apt-packages tests passed"
exit "$failures"
