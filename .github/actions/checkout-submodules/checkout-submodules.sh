#!/usr/bin/env bash
# Initialize the caller's git submodules (all of them, or only the paths in
# SUBMODULE_PATHS). Kept as a script so tests can run it against throwaway
# repositories. See action.yml for the inputs.
set -euo pipefail

# With a token, rewrite submodule URLs to authenticate the clone.
# Without one, note and proceed: public submodules clone anonymously,
# and a truly private submodule will fail naturally at checkout.
if [ -z "${SUBMODULES_TOKEN:-}" ]; then
  echo "::notice::SUBMODULES_TOKEN is empty; cloning submodules anonymously (works for public submodules; a private one will fail at checkout)."
else
  # --global (not --local) is intentional: the rewrite must also apply
  # to the nested clones from `--recursive`, which run in each
  # submodule's own repo context and would not see a superproject-local
  # insteadOf. It only rewrites HTTPS github.com clones and lives only
  # on this job's ephemeral runner (~/.gitconfig), so it does not leak
  # beyond the job.
  git config --global url."https://x-access-token:${SUBMODULES_TOKEN}@github.com/".insteadOf "https://github.com/"
fi

# Split the whitespace-separated path list into an array; an empty list
# leaves the array empty, which selects every submodule.
# Newlines count as separators too, so a multi-line YAML block works.
read -r -a paths <<< "$(printf '%s' "${SUBMODULE_PATHS:-}" | tr -s '[:space:]' ' ')"
if [ "${#paths[@]}" -gt 0 ]; then
  echo "Initializing submodules: ${paths[*]}"
  git submodule update --init --recursive --depth 1 -- "${paths[@]}"
else
  git submodule update --init --recursive --depth 1
fi
