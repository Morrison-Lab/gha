#!/usr/bin/env bash
# The "Plan the cluster render" step of quarto-publish/action.yml: writes the
# `steps` output for condor-batch from the render step's environment variables.
# The job has no runner environment, so each variable becomes a quoted
# assignment on the command line, as in preview/plan-cluster-render.sh (gha#1563).
set -euo pipefail
helpers=.gha-render
rm -rf "$helpers"
mkdir -p "$helpers"
cp "$GITHUB_ACTION_PATH/render-site.sh" "$GITHUB_ACTION_PATH/redirect-stubs.py" \
  "$GITHUB_ACTION_PATH/render-per-file.py" "$helpers/"
cp -r "$GITHUB_ACTION_PATH/per_file" "$helpers/per_file"
cp "$GITHUB_ACTION_PATH/install-cluster-r-packages.R" "$helpers/"
rm -rf "$helpers/per_file/__pycache__"
assign=""
for name in PROJECT_PATH OUTPUT_DIR RENDER_PROFILE FORMATS PER_FILE_FORMATS \
  FAIL_ON_WARN FORBID_PATTERNS SETUP_JULIA; do
  assign+=" $name=$(printf '%q' "${!name}")"
done
# The image has its own R library, so install the caller's `r-packages` that
# it lacks into a library in the job's scratch directory first (gha#2007).
install=""; rlib=""
if [ -n "${R_PACKAGES:-}" ]; then
  printf '%s\n' "$R_PACKAGES" > "$helpers/r-packages.txt"
  install="Rscript $helpers/install-cluster-r-packages.R \"\$PWD/.gha-rlib\" $helpers/r-packages.txt"
  rlib=" R_LIBS=\"\$PWD/.gha-rlib\""
fi
# A PDF render needs a writable TeX cache under the checkout, since the job
# has no usable home (epi202#28), as in preview/plan-cluster-render.sh.
render="mkdir -p \"\$PWD/.texvar\" && env TEXMFVAR=\"\$PWD/.texvar\" TEXMFCACHE=\"\$PWD/.texvar\"$rlib$assign PER_FILE_SCRIPT=$helpers/render-per-file.py REDIRECT_STUBS_SCRIPT=$helpers/redirect-stubs.py bash $helpers/render-site.sh"
# condor-batch bundles two or more steps; the second one fails the job when
# the render left no output directory.
check="test -d $(printf '%q' "$PROJECT_PATH/$OUTPUT_DIR")"
{
  echo "steps<<GHA_CLUSTER_STEPS"
  [ -z "$install" ] || echo "$install"
  echo "$render"
  echo "$check"
  echo "GHA_CLUSTER_STEPS"
} >> "$GITHUB_OUTPUT"
