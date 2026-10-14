#!/usr/bin/env bash
# Offline tests for checkout-submodules.sh: build a superproject with two local
# submodules in a temp dir and check which ones the script initializes.
# Nothing is committed; the fixture is generated at run time.
set -uo pipefail

script="$(cd "$(dirname "$0")/.." && pwd)/checkout-submodules.sh"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
fails=0

export GIT_CONFIG_GLOBAL="$tmp/gitconfig"
git config --global protocol.file.allow always
git config --global user.name tester
git config --global user.email tester@example.invalid  # phi-allow
git config --global init.defaultBranch main

for name in pub priv; do
  git init -q "$tmp/$name"
  echo "$name" > "$tmp/$name/f.txt"
  git -C "$tmp/$name" add f.txt
  git -C "$tmp/$name" commit -q -m init
done
git init -q "$tmp/super"
git -C "$tmp/super" submodule add -q "$tmp/pub" pub
git -C "$tmp/super" submodule add -q "$tmp/priv" priv
git -C "$tmp/super" commit -q -m subs

fresh_clone() {
  rm -rf "$tmp/work"
  git clone -q "$tmp/super" "$tmp/work"
}

# run_case NAME PATHS EXPECT_PUB EXPECT_PRIV
run_case() {
  local name=$1 paths=$2 want_pub=$3 want_priv=$4
  fresh_clone
  (cd "$tmp/work" && SUBMODULES_TOKEN='' SUBMODULE_PATHS="$paths" bash "$script" > "$tmp/out.txt" 2>&1)
  local rc=$?
  local got_pub=no got_priv=no
  [ -f "$tmp/work/pub/f.txt" ] && got_pub=yes
  [ -f "$tmp/work/priv/f.txt" ] && got_priv=yes
  if [ "$rc" -ne 0 ] || [ "$got_pub" != "$want_pub" ] || [ "$got_priv" != "$want_priv" ]; then
    echo "::error::$name: rc=$rc pub=$got_pub (want $want_pub) priv=$got_priv (want $want_priv)"
    sed 's/^/    /' "$tmp/out.txt"
    fails=$((fails + 1))
  else
    echo "ok: $name"
  fi
}

run_case "empty paths initialize every submodule" "" yes yes
run_case "one path initializes only that submodule" "pub" yes no
run_case "other path initializes only the other" "priv" no yes
run_case "two paths, extra whitespace" "  pub   priv " yes yes

# A named path that is not a submodule must fail, not silently check out nothing.
fresh_clone
if (cd "$tmp/work" && SUBMODULES_TOKEN='' SUBMODULE_PATHS="nonexistent" bash "$script" > /dev/null 2>&1); then
  echo "::error::unknown path was accepted"
  fails=$((fails + 1))
else
  echo "ok: unknown path fails"
fi

if [ "$fails" -ne 0 ]; then
  echo "::error::$fails case(s) failed"
  exit 1
fi
echo "all cases passed"
