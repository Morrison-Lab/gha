#!/usr/bin/env bash
#
# Fail when a repository TRACKS operating-system or editor detritus -- a
# `.DS_Store` written by Finder, an AppleDouble `._*` sidecar, an `.Rhistory`
# an IDE dropped in the project root.
#
# Two design choices are load-bearing.
#
# The matching is done by GIT, not by this script. `git ls-files -i -c -X`
# lists tracked files matching a set of gitignore patterns, so the patterns
# input is ordinary gitignore syntax and a hand-rolled glob matcher never
# enters the picture. Standard exclude sources are opt-in for `git ls-files`
# (`--exclude-standard`), which is deliberately NOT passed: a file the caller
# force-added despite its own `.gitignore` is a decision this check has no
# business second-guessing, and including standard excludes would flag every
# one of them. Verified against git 2.50.1: without the flag, a force-added
# `build.log` listed in `.gitignore` is not reported; with it, it is.
#
# The scan covers TRACKED FILES AT HEAD rather than the pull request's diff.
# The diff-scoping that check-phi and check-new-line-breaks use exists so a
# corpus's pre-existing drift is not re-flagged on every unrelated PR; that
# rationale does not transfer here, because a `.DS_Store` committed two years
# ago is still a live defect and still costs exactly one `git rm --cached` to
# clear. `paths-ignore` is the escape hatch for a tree that genuinely wants to
# keep one.
set -euo pipefail

target="${JUNK_TARGET:-${GITHUB_WORKSPACE:-.}}"

if [ ! -d "$target/.git" ] && ! git -C "$target" rev-parse --git-dir >/dev/null 2>&1; then
  echo "::error::check-junk-files: '$target' is not a git repository."
  exit 1
fi

# Fail closed, and normalize before deciding: only an explicit "false" opts
# out. Matches check-secrets and check-phi, so `fail: 'True'`, `fail: 'yes'`,
# or a trailing space cannot quietly downgrade the gate to advisory.
fail_raw="${JUNK_FAIL:-true}"
fail_normalized="$(printf '%s' "$fail_raw" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
if [ "$fail_normalized" = "false" ]; then
  fail=false
else
  fail=true
fi

work="${RUNNER_TEMP:-/tmp}/check-junk-files"
mkdir -p "$work"
pattern_file="$work/patterns.txt"

# Split on commas as well as newlines, strip `#` comments and surrounding
# whitespace, and drop blanks. Commas are safe separators here in a way they
# are not for check-secrets' regex allowlist: gitignore syntax has no bounded
# quantifier, so a comma inside a pattern is not a thing anyone writes.
printf '%s\n' "${JUNK_PATTERNS:-}" \
  | tr ',' '\n' \
  | sed -e 's/[[:space:]]*#.*$//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' \
  | grep -v '^$' > "$pattern_file" || :

# An empty pattern set makes `git ls-files -i` match nothing and exit 0, which
# is a green check that examined no patterns at all -- the failure mode this
# whole capability exists to prevent, arriving through its own configuration.
# Refuse it rather than reporting a vacuous all-clear.
if [ ! -s "$pattern_file" ]; then
  echo "::error::check-junk-files: the patterns input is empty after parsing, so nothing would be checked. Supply at least one gitignore-style pattern, or remove this job."
  exit 1
fi

# `paths-ignore` entries become git PATHSPEC exclusions rather than `!` lines
# appended to the pattern file. That is not a stylistic preference: gitignore
# negation is matched per pattern against the full path, so `!vendor/` fails
# to re-include `vendor/.DS_Store` and silently suppresses nothing, whereas
# the pathspec `:(exclude)vendor/` excludes the directory as written.
# Verified against git 2.50.1, both directions.
pathspecs=()
while IFS= read -r entry; do
  [ -n "$entry" ] && pathspecs+=(":(exclude)$entry")
done < <(
  printf '%s\n' "${JUNK_PATHS_IGNORE:-}" \
    | tr ',' '\n' \
    | sed -e 's/[[:space:]]*#.*$//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' \
    | grep -v '^$' || :
)

tracked_count="$(git -C "$target" ls-files | wc -l | tr -d '[:space:]')"

matches=()
while IFS= read -r -d '' path; do
  matches+=("$path")
done < <(git -C "$target" ls-files -z -i -c -X "$pattern_file" -- "${pathspecs[@]+"${pathspecs[@]}"}")

pattern_count="$(wc -l < "$pattern_file" | tr -d '[:space:]')"
match_count="${#matches[@]}"

# Report what was EXAMINED alongside what was found. A bare "0 findings" is
# indistinguishable from a scan that ran against an empty index or a pathspec
# that excluded everything.
echo "check-junk-files: $tracked_count tracked file(s) examined against $pattern_count pattern(s); $match_count match(es)."

if [ "$match_count" -eq 0 ]; then
  echo "No junk files are tracked."
  exit 0
fi

if [ "$fail" = "true" ]; then
  annotation_level=error
else
  annotation_level=warning
fi

for path in "${matches[@]}"; do
  echo "::${annotation_level} file=${path}::check-junk-files: '${path}' is tracked but looks like operating-system or editor detritus. Remove it with: git rm --cached '${path}'"
done

# Cap the ready-to-paste removal command. A tree with hundreds of these wants
# one command per directory anyway, and a multi-kilobyte line in a job summary
# is unreadable.
rm_limit=20
rm_args=""
shown=0
for path in "${matches[@]}"; do
  [ "$shown" -ge "$rm_limit" ] && break
  rm_args="$rm_args '$path'"
  shown=$((shown + 1))
done

{
  echo "### check-junk-files"
  echo ""
  echo "$match_count tracked file(s) look like operating-system or editor detritus."
  echo ""
  echo "| File |"
  echo "| --- |"
  for path in "${matches[@]}"; do
    echo "| \`$path\` |"
  done
  echo ""
  echo "#### Fix it in this repository"
  echo ""
  echo '```sh'
  echo "git rm --cached$rm_args"
  if [ "$match_count" -gt "$rm_limit" ]; then
    echo "# ... and $((match_count - rm_limit)) more; see the table above."
  fi
  echo '```'
  echo ""
  echo "Then add the patterns to the repository's \`.gitignore\` so they do not come back."
  echo ""
  echo "#### Fix it on your machine, so it stops recurring everywhere"
  echo ""
  echo "A repository-level \`.gitignore\` only protects this repository. A global"
  echo "one protects every repository you clone:"
  echo ""
  echo '```sh'
  echo "git config --global core.excludesFile ~/.gitignore"
  echo "printf '.DS_Store\\n' >> ~/.gitignore"
  echo '```'
  echo ""
  echo "R users can do the same in one call, which also covers \`.Rproj.user\`,"
  echo "\`.Rhistory\`, \`.Rdata\`, \`.httr-oauth\`, and \`.quarto\`:"
  echo ""
  echo '```r'
  echo "usethis::git_vaccinate()"
  echo '```'
  echo ""
  echo "See <https://usethis.r-lib.org/reference/git_vaccinate.html>. Note that"
  echo "vaccination does **not** cover \`._*\` AppleDouble sidecars, \`Thumbs.db\`,"
  echo "or \`desktop.ini\`, which this check flags by default -- add those to your"
  echo "global \`.gitignore\` by hand."
  echo ""
  echo "A file that genuinely belongs in the tree is exempted with the"
  echo "\`paths-ignore\` input."
} >> "${GITHUB_STEP_SUMMARY:-/dev/null}"

if [ "$fail" = "true" ]; then
  echo "::error::check-junk-files: $match_count tracked file(s) look like operating-system or editor detritus."
  exit 1
fi

echo "::warning::check-junk-files: $match_count tracked file(s) look like operating-system or editor detritus (fail: false, so not blocking)."
