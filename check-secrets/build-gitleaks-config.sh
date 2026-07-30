#!/usr/bin/env bash
#
# Write the gitleaks config the scan runs under, to SECRETS_GENERATED_CONFIG.
#
# The config is generated rather than shipped because two of the action's
# inputs (paths-ignore, allowlist-file) are gitleaks allowlist entries, and
# gitleaks accepts allowlists only through its config file.
#
# It always extends something, so the generated file adds to the caller's rules
# rather than replacing them: SECRETS_CONFIG when the caller named a config,
# and gitleaks' built-in default ruleset otherwise.
#
# Kept as a standalone script, rather than inline in action.yml, so the TOML it
# emits can be tested offline -- see check-secrets/tests/.
set -euo pipefail

: "${SECRETS_GENERATED_CONFIG:?SECRETS_GENERATED_CONFIG is required}"
: "${SECRETS_TARGET:?SECRETS_TARGET is required}"

paths_ignore="${SECRETS_PATHS_IGNORE:-}"
allowlist_file="${SECRETS_ALLOWLIST_FILE:-}"
base_config="${SECRETS_CONFIG:-}"

# gitleaks auto-detects `(target)/.gitleaks.toml` only when no --config is
# given, and the scan always passes one, so pick the conventional locations up
# here instead. Naming either input explicitly overrides this.
if [ -z "$base_config" ] && [ -f "$SECRETS_TARGET/.gitleaks.toml" ]; then
  base_config="$SECRETS_TARGET/.gitleaks.toml"
fi
if [ -z "$allowlist_file" ] && [ -f "$SECRETS_TARGET/.github/secrets-allowlist.txt" ]; then
  allowlist_file="$SECRETS_TARGET/.github/secrets-allowlist.txt"
fi

work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT

# TOML literal strings are delimited by ''' and have no escape sequences, so a
# pattern containing ''' would truncate the array and change which findings are
# suppressed. Refuse it rather than emit a config meaning something other than
# what was asked for.
reject_toml_delimiter() {
  local pattern="$1" source="$2"
  case "$pattern" in
    *"'''"*)
      echo "::error::check-secrets: a pattern from $source contains ''', which cannot appear in a TOML literal string." >&2
      exit 1
      ;;
  esac
}

# Normalize a pattern source into one pattern per line, dropping blank lines
# and # comments.
#
# $1 is the output file; $2 is "commas" to also treat a comma as a separator,
# or "newlines" to split on newlines alone. That distinction is load-bearing
# rather than tidy. A composite action's inputs are single strings, so
# `paths-ignore` genuinely needs a comma separator, and a pattern needing a
# literal comma there can use \x2c. An allowlist FILE is documented as one
# regex per line, where a comma is ordinary regex syntax: comma-splitting
# `AKIA[0-9A-Z]{16,20}` yields `AKIA[0-9A-Z]{16` and `20}`, both of which
# compile, so nothing errors -- the intended suppression just stops matching
# while the `20}` fragment becomes its own unanchored allowlist entry. That is
# the quiet-widening failure this file's header warns about (gha#385 review).
#
# grep exits 1 when every line is filtered out, which is an empty result rather
# than a failure, so tolerate it here instead of letting errexit abort.
split_patterns() {
  local out="$1" mode="$2"
  if [ "$mode" = "commas" ]; then
    tr ',' '\n'
  else
    cat
  fi \
    | sed 's/^[[:space:]]*//; s/[[:space:]]*$//' \
    | { grep -v -e '^#' -e '^$' || true; } \
    > "$out"
}

# gitleaks matches allowlist paths with an unanchored regexp.MatchString, so a
# glob-shaped pattern is a silent over-suppression rather than an error. `**`
# does fail to compile (Go rejects nested repetition), but `docs/*` is a valid
# regex meaning "doc" followed by any number of `s`... and, unanchored, it
# matches every path containing `docs` -- `mydocs-secrets.env` included.
# Warn rather than reject: `.*\.pem` is a legitimate pattern ending in a
# repetition operator, so there is no rule here that is both safe and exact.
warn_if_glob_shaped() {
  local pattern="$1" source="$2"
  case "$pattern" in
    *'**'* | */'*')
      echo "::warning::check-secrets: '$pattern' from $source looks like a glob, but these are Go regexes matched unanchored. '**' will fail to compile; a trailing '/*' silently matches every path containing the prefix. Drop the '*', or anchor with '^'." >&2
      ;;
  esac
}

# Writes to stdout, and is called from inside a brace group whose output is
# redirected -- never from a command substitution. A brace group runs in the
# current shell, so a rejected pattern's `exit 1` ends the script. A bare
# `entries="$(emit_array_entries ...)"` would in fact still abort, since the
# assignment takes the substitution's status and errexit acts on it, but
# `local entries="$(...)"` would not, because `local`'s own status is 0.
# Measured on bash 5.2: the first form exits 1, the second continues.
# Keeping the value out of a substitution sidesteps that distinction entirely.
emit_array_entries() {
  local patterns_file="$1" source="$2" check_globs="$3" pattern
  while IFS= read -r pattern; do
    reject_toml_delimiter "$pattern" "$source"
    if [ "$check_globs" = "check-globs" ]; then
      warn_if_glob_shaped "$pattern" "$source"
    fi
    printf "  '''%s''',\n" "$pattern"
  done < "$patterns_file"
}

mkdir -p "$(dirname "$SECRETS_GENERATED_CONFIG")"

{
  echo "# Generated by Morrison-Lab/gha check-secrets. Do not edit."
  echo ""
  echo "[extend]"
} > "$SECRETS_GENERATED_CONFIG"

if [ -n "$base_config" ]; then
  if [ ! -f "$base_config" ]; then
    echo "::error::check-secrets: config file '$base_config' does not exist." >&2
    exit 1
  fi
  reject_toml_delimiter "$base_config" "the config input"
  echo "path = '''$base_config'''" >> "$SECRETS_GENERATED_CONFIG"
else
  echo "useDefault = true" >> "$SECRETS_GENERATED_CONFIG"
fi

if [ -n "$paths_ignore" ]; then
  printf '%s' "$paths_ignore" | split_patterns "$work_dir/paths.txt" commas
  if [ -s "$work_dir/paths.txt" ]; then
    # A brace group is not a subshell, so emit_array_entries' `exit 1` on a
    # rejected pattern still ends the script from inside it.
    {
      echo ""
      echo "[[allowlists]]"
      echo 'description = "check-secrets paths-ignore input"'
      echo "paths = ["
      emit_array_entries "$work_dir/paths.txt" "the paths-ignore input" check-globs
      echo "]"
    } >> "$SECRETS_GENERATED_CONFIG"
  fi
fi

if [ -n "$allowlist_file" ]; then
  if [ ! -f "$allowlist_file" ]; then
    echo "::error::check-secrets: allowlist file '$allowlist_file' does not exist." >&2
    exit 1
  fi
  split_patterns "$work_dir/allow.txt" newlines < "$allowlist_file"
  if [ -s "$work_dir/allow.txt" ]; then
    {
      echo ""
      echo "[[allowlists]]"
      echo "description = \"check-secrets allowlist file\""
      # regexTarget "match" targets the whole matched text rather than only the
      # extracted secret, mirroring check-phi's allowlist semantics: a finding
      # whose text matches any regex is suppressed.
      echo 'regexTarget = "match"'
      echo "regexes = ["
      emit_array_entries "$work_dir/allow.txt" "$allowlist_file" no-glob-check
      echo "]"
    } >> "$SECRETS_GENERATED_CONFIG"
  fi
fi

echo "Wrote gitleaks config to $SECRETS_GENERATED_CONFIG"
