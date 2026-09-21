#!/usr/bin/env bash
# Checkout reference repositories for AI review and agent workflows.
#
# Usage:
#   REPOS="owner/repo[@ref] ..." TARGET_DIR_NAME=".reference-repos" \
#   CURRENT_REPO="owner/repo" [TOKEN="..."] bash checkout-reference-repos.sh
#
# Outputs:
#   Sets dir, repos, and guidance on $GITHUB_OUTPUT if GITHUB_OUTPUT is set.
set -euo pipefail

REPOS="${REPOS:-}"
TARGET_DIR_NAME="${TARGET_DIR_NAME:-.reference-repos}"
TOKEN="${TOKEN:-}"
CURRENT_REPO="${CURRENT_REPO:-}"
WORKSPACE="${GITHUB_WORKSPACE:-$(pwd)}"

# Normalize and clean repo list: replace commas and newlines with spaces
CLEAN_REPOS=$(printf '%s' "$REPOS" | tr ',\n' '  ')

set_output() {
  local key="$1"
  local val="$2"
  if [ -n "${GITHUB_OUTPUT:-}" ]; then
    echo "$key=$val" >> "$GITHUB_OUTPUT"
  fi
}

if [ -z "${CLEAN_REPOS//[[:space:]]/}" ]; then
  set_output "dir" ""
  set_output "repos" ""
  if [ -n "${GITHUB_OUTPUT:-}" ]; then
    DELIM="refrepo_$(openssl rand -hex 8 2>/dev/null || date +%s)"
    {
      echo "guidance<<$DELIM"
      echo "$DELIM"
    } >> "$GITHUB_OUTPUT"
  fi
  exit 0
fi

TARGET_DIR="$WORKSPACE/$TARGET_DIR_NAME"
mkdir -p "$TARGET_DIR"

# Ensure target directory is ignored by git in the parent repository
# so git status, git diff, and untracked file scans stay clean.
# Works in regular repositories, submodules, and worktrees.
if git -C "$WORKSPACE" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  EXCLUDE_FILE="$(git -C "$WORKSPACE" rev-parse --git-path info/exclude)"
  mkdir -p "$(dirname "$EXCLUDE_FILE")"
  if ! grep -qs "^/$TARGET_DIR_NAME/" "$EXCLUDE_FILE" 2>/dev/null; then
    echo "/$TARGET_DIR_NAME/" >> "$EXCLUDE_FILE"
  fi
fi

CLONED_LIST=""
GUIDANCE_ITEMS=""
declare -A SEEN_REPOS=()

for item in $CLEAN_REPOS; do
  [ -z "$item" ] && continue

  # Parse repo and optional ref: owner/repo@ref or owner/repo
  REPO_SPEC="${item%@*}"
  REF=""
  if [[ "$item" == *"@"* ]]; then
    REF="${item##*@}"
  fi

  # Strip leading/trailing URLs or suffixes if someone passed https://github.com/owner/repo
  REPO_SPEC="${REPO_SPEC#https://github.com/}"
  REPO_SPEC="${REPO_SPEC#http://github.com/}"
  REPO_SPEC="${REPO_SPEC%.git}"

  # If the reference repo is the repository currently being checked/reviewed, skip self-clone
  if [ -n "$CURRENT_REPO" ] && [ "${REPO_SPEC,,}" = "${CURRENT_REPO,,}" ]; then
    echo "::notice::Skipping self-clone of current repository $REPO_SPEC in reference-repos."
    continue
  fi

  # Avoid duplicate clone and guidance entries for duplicated inputs
  if [ -n "${SEEN_REPOS["$REPO_SPEC"]:-}" ]; then
    continue
  fi
  SEEN_REPOS["$REPO_SPEC"]=1

  DEST="$TARGET_DIR/$REPO_SPEC"

  if [ -d "$DEST" ]; then
    echo "::notice::Reference repo $REPO_SPEC already exists at $DEST; skipping checkout."
  else
    echo "Checking out reference repo $REPO_SPEC into $DEST..."
    mkdir -p "$DEST"
    git init -q "$DEST"
    git -C "$DEST" remote add origin "https://github.com/${REPO_SPEC}.git"

    FETCH_ENV=()
    if [ -n "$TOKEN" ]; then
      FETCH_ENV=(
        "GIT_CONFIG_COUNT=1"
        "GIT_CONFIG_KEY_0=url.https://x-access-token:${TOKEN}@github.com/.insteadOf"
        "GIT_CONFIG_VALUE_0=https://github.com/"
      )
    fi

    FETCH_TARGET="HEAD"
    if [ -n "$REF" ]; then
      FETCH_TARGET="$REF"
    fi

    if env "${FETCH_ENV[@]}" git -C "$DEST" fetch --depth 1 origin "$FETCH_TARGET" >/dev/null 2>&1 && \
       git -C "$DEST" checkout -q FETCH_HEAD >/dev/null 2>&1; then
      echo "Successfully checked out $REPO_SPEC."
    else
      echo "::warning::Failed to check out reference repository $REPO_SPEC; proceeding with remaining repos."
      rm -rf "$DEST"
      continue
    fi
  fi

  if [ -z "$CLONED_LIST" ]; then
    CLONED_LIST="$REPO_SPEC"
  else
    CLONED_LIST="$CLONED_LIST, $REPO_SPEC"
  fi

  GUIDANCE_ITEMS="${GUIDANCE_ITEMS}- \`$REPO_SPEC\` is available locally at \`$TARGET_DIR_NAME/$REPO_SPEC\`\n"
done

set_output "dir" "$TARGET_DIR_NAME"
set_output "repos" "$CLONED_LIST"

if [ -n "${GITHUB_OUTPUT:-}" ]; then
  DELIM="refrepo_$(openssl rand -hex 8 2>/dev/null || date +%s)"
  {
    echo "guidance<<$DELIM"
    if [ -n "$GUIDANCE_ITEMS" ]; then
      printf "**Reference Repositories Available**:\n"
      printf "The following external reference repositories were checked out into your workspace:\n"
      printf "%b" "$GUIDANCE_ITEMS"
      printf "Inspect their source files, schemas, workflows, or guides using \`Read\`, \`Glob\`, or \`Grep\` to confirm external references or conventions.\n"
    fi
    echo "$DELIM"
  } >> "$GITHUB_OUTPUT"
fi
