#!/usr/bin/env bash
#
# Offline suite for check-diff-scoped.sh, driven against throwaway git repos in
# $TMPDIR -- nothing committed, per this repo's generate-fixtures-at-runtime
# rule (a committed fixture is swept into the bib/phi/typos jobs' own scans).
#
# The checks it wraps are stubbed rather than real: the wrapper's job is to
# decide WHETHER a check may be trusted to have run, so the suite has to
# control each check's outcome independently of whether python, typos, or a
# real finding happens to be present on the machine running it.
#
# The REFUSAL cases are the ones to keep if this is ever trimmed. Every one of
# them fails in the same direction: a wrapper that runs anyway prints no
# findings, and no findings is indistinguishable from a clean verdict. That is
# the exact confusion the wrapper exists to prevent, so each refusal is
# asserted on its exit status rather than on its wording.
set -uo pipefail

SCRIPT="${SCRIPT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/check-diff-scoped.sh}"
[ -f "$SCRIPT" ] || { echo "::error::suite: cannot find check-diff-scoped.sh at $SCRIPT"; exit 1; }
# Absolutize it. Every case cd's into a throwaway fixture repo before invoking
# the script, so a RELATIVE override resolves against that fixture instead and
# fails every case that reaches the script -- which reads as "the
# implementation is broken"
# rather than as "the harness was pointed at nothing". The default is already
# absolute; this only rescues an override passed the natural way.
SCRIPT="$(cd "$(dirname "$SCRIPT")" && pwd)/$(basename "$SCRIPT")"

pass=0; fail=0
ok()   { printf 'PASS: %s\n' "$1"; pass=$((pass+1)); }
bad()  { printf '::error::FAIL: %s -- %s\n' "$1" "$2"; fail=$((fail+1)); }

# A fixture repo with one commit, an origin/HEAD, and stub check scripts whose
# exit status the caller chooses.
make_repo() {
  local d nlb_rc="${1:-0}"
  d="$(mktemp -d)"
  (
    cd "$d"
    git init -q -b main .
    # A synthetic identity for a throwaway fixture repo, never a real address.
    git config user.email t@example.invalid; git config user.name Tester  # phi-allow
    mkdir -p check-new-line-breaks check-phi
    printf 'import sys; sys.exit(%s)\n' "$nlb_rc" > check-new-line-breaks/check-new-line-breaks.py
    printf 'import sys; sys.exit(0)\n'            > check-phi/check-phi.py
    printf '# fixture\n' > README.md
    printf 'ignored-output/\n' > .gitignore
    git add -A; git commit -qm base
    # A second commit so HEAD~1 exists and origin/main can point at the first.
    printf 'more\n' >> README.md; git add -A; git commit -qm second
    git remote add origin "$d"
    git update-ref refs/remotes/origin/main HEAD~1
    git symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/main
  ) >/dev/null 2>&1
  printf '%s' "$d"
}
run() { ( cd "$1" && shift && bash "$SCRIPT" "$@" >/tmp/dsout 2>&1; echo $?; ); }

# 1. Clean tree, resolvable base ref, all stubs clean, typos absent.
#    Exit 3 rather than 0: a check that could not run is not a check that
#    passed, and collapsing the two is the wrapper's whole subject.
d=$(make_repo 0); rc=$(run "$d" origin/main)
[ "$rc" = 3 ] && ok "clean tree, typos unavailable => 3 (incomplete, not clean)" \
             || bad "clean/unavailable" "expected 3, got $rc"
grep -q 'did not run' /tmp/dsout && ok "the run says which checks did not run" \
                                  || bad "unavailable naming" "no did-not-run summary"
rm -rf "$d"

# 1b. Script PRESENT but its required binary absent is a different reason from
#     script absent, and the wrapper must not collapse them: one is a missing
#     capability, the other a missing install, and they are fixed differently.
d=$(make_repo 0)
mkdir -p "$d/check-typos"; printf 'import sys; sys.exit(0)\n' > "$d/check-typos/check-typos.py"
( cd "$d" && git add -A && git commit -qm typos-stub ) >/dev/null 2>&1
rc=$( cd "$d" && PATH=/usr/bin:/bin env -u TYPOS_BIN_DIR bash "$SCRIPT" origin/main >/tmp/dsout 2>&1; echo $?; )
grep -q 'UNAVAILABLE' /tmp/dsout && ok "tool absent reports UNAVAILABLE, not SKIP" \
                                 || bad "probe path" "expected UNAVAILABLE, got: $(grep typos /tmp/dsout | head -1)"
# Assert the STATUS too, not just the wording. Without this the tool arm's
# bookkeeping can be deleted outright: the suite stays green and the wrapper
# returns 0 over a check that never ran, which is the one outcome it exists to
# prevent. Case 1 exercises only the script-absent arm, so it cannot see this.
[ "$rc" = 3 ] && ok "tool absent is unavailable (3), never clean" \
              || bad "probe exit" "expected 3, got $rc"
rm -rf "$d"

# 2. An untracked file must refuse. This is the gha#740 case verbatim.
d=$(make_repo 0); printf 'x\n' > "$d/new.md"; rc=$(run "$d" origin/main)
[ "$rc" = 2 ] && ok "untracked file => refuse (2)" || bad "untracked" "expected 2, got $rc"
grep -q 'new.md' /tmp/dsout && ok "the unexamined path is named" \
                            || bad "untracked naming" "path not printed"
rm -rf "$d"

# 3. A STAGED modification must refuse too. Staging feels like progress toward
#    committing, which is exactly why it reads as safe and is not.
d=$(make_repo 0); printf 'edit\n' >> "$d/README.md"; ( cd "$d" && git add -A ) >/dev/null
rc=$(run "$d" origin/main)
[ "$rc" = 2 ] && ok "staged modification => refuse (2)" || bad "staged" "expected 2, got $rc"
rm -rf "$d"

# 4. A gitignored file must NOT refuse: build output is not unexamined content,
#    and refusing on it would make the wrapper unusable and get it bypassed.
d=$(make_repo 0); mkdir -p "$d/ignored-output"; printf 'x\n' > "$d/ignored-output/a.md"
rc=$(run "$d" origin/main)
[ "$rc" != 2 ] && ok "gitignored file does not refuse" || bad "gitignored" "refused on ignored content"
rm -rf "$d"

# 5. The override proceeds, and still says what it is not examining -- an
#    escape valve that hid the gap would be worse than no valve.
d=$(make_repo 0); printf 'x\n' > "$d/new.md"
rc=$( cd "$d" && DIFF_SCOPED_ALLOW_DIRTY=1 bash "$SCRIPT" origin/main >/tmp/dsout 2>&1; echo $?; )
[ "$rc" != 2 ] && ok "override proceeds past a dirty tree" || bad "override" "still refused"
grep -q 'WARNING' /tmp/dsout && ok "override still reports the gap" \
                             || bad "override silence" "no WARNING printed"
rm -rf "$d"

# 6. An unresolvable base ref refuses rather than passing an empty ref through.
#    The wrapped checks disagree about what empty means -- two skip, one scans
#    the whole tree -- so passing it through yields a different wrong answer per
#    check and no error anywhere.
d=$(make_repo 0); rc=$(run "$d" origin/does-not-exist)
[ "$rc" = 2 ] && ok "unresolvable base ref => refuse (2)" || bad "bad ref" "expected 2, got $rc"
# Pin which message, not just that it refuses. The merge-base gate below also
# rejects a nonexistent ref (git merge-base exits 128), so the resolvability
# check earns its place only by naming the actual problem -- and a mutation
# removing it leaves the exit status unchanged.
grep -q 'does not resolve to a commit' /tmp/dsout && ok "it names the ref as unresolvable" \
                                                  || bad "bad ref reason" "refused with a different message"
rm -rf "$d"

# 7. No base ref and no origin/HEAD refuses rather than guessing 'main'.
d=$(make_repo 0); ( cd "$d" && git symbolic-ref -d refs/remotes/origin/HEAD ) >/dev/null 2>&1
rc=$( cd "$d" && env -u DIFF_SCOPED_BASE_REF bash "$SCRIPT" >/tmp/dsout 2>&1; echo $?; )
[ "$rc" = 2 ] && ok "no base ref and no origin/HEAD => refuse (2)" || bad "no ref" "expected 2, got $rc"
# Assert the REASON, not just the refusal. Deleting the no-base-ref block
# entirely still yields exit 2, because the resolvability check then fails on
# an empty ref -- so without this the case pins nothing about the branch it
# names, and the remedy it prints is the whole value of that branch.
grep -q 'origin/HEAD is not set' /tmp/dsout && ok "it names the remedy for a clone with no origin/HEAD" \
                                            || bad "no-ref reason" "refused for a different reason"
rm -rf "$d"

# 8. A real finding outranks an incomplete run: 1, not 3. The finding is
#    actionable now, and reporting 3 would bury it behind a tooling gap.
d=$(make_repo 1); rc=$(run "$d" origin/main)
[ "$rc" = 1 ] && ok "a finding outranks the incomplete run (1, not 3)" \
             || bad "finding precedence" "expected 1, got $rc"
rm -rf "$d"

# 9. A missing check script counts as unavailable, never as a silent pass.
d=$(make_repo 0)
# Commit the removal: deleting a TRACKED file dirties the tree, so the dirty
# guard would fire first and this case would silently measure that guard
# instead of the missing-script path it is named for.
( cd "$d" && git rm -q check-phi/check-phi.py && git commit -qm drop-phi ) >/dev/null 2>&1
rc=$(run "$d" origin/main)
[ "$rc" = 3 ] && ok "a missing check script is unavailable, not a pass" \
             || bad "missing script" "expected 3, got $rc"
grep -q 'phi' /tmp/dsout && ok "the missing check is named" || bad "missing naming" "phi not named"
rm -rf "$d"

# 10. status.showUntrackedFiles=no must not blind the dirty guard. A bare
#     `git status --porcelain` obeys that setting, so one line of contributor
#     config made an untracked file invisible and turned case 2 -- the gha#740
#     case verbatim -- into a clean exit 3, with nothing saying so.
d=$(make_repo 0)
( cd "$d" && git config status.showUntrackedFiles no ) >/dev/null 2>&1
printf 'x\n' > "$d/new.md"
rc=$(run "$d" origin/main)
[ "$rc" = 2 ] && ok "status.showUntrackedFiles=no does not blind the dirty guard" \
              || bad "showUntrackedFiles" "expected 2, got $rc"
rm -rf "$d"

# 11. A base ref that RESOLVES but shares no history with HEAD must refuse.
#     Resolving is strictly weaker than sharing history, and the gap is the
#     whole failure this wrapper exists to prevent: given such a ref,
#     check-new-line-breaks and check-typos return 0 without examining
#     anything and check-phi scans the whole tree, so all three read as OK.
#     A shallow clone is the ordinary route to this state.
d=$(make_repo 0)
orphan=$(
  cd "$d" || exit
  {
    git checkout --orphan unrelated
    git rm -rq --cached .
    printf 'z\n' > O.md
    git add O.md
    git commit -qm orphan
  } >/dev/null 2>&1
  git rev-parse HEAD
)
( cd "$d" && git checkout -qf main ) >/dev/null 2>&1
[ -n "$orphan" ] || bad "unrelated setup" "fixture produced no orphan commit"
rc=$(run "$d" "$orphan")
[ "$rc" = 2 ] && ok "a base ref sharing no history with HEAD => refuse (2)" \
              || bad "unrelated history" "expected 2, got $rc"
grep -q 'shares no reachable history' /tmp/dsout && ok "it names the shallow-clone remedy" \
                                                 || bad "unrelated reason" "refused for a different reason"
rm -rf "$d"

printf '\n%s passed, %s failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
