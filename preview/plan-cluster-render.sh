#!/usr/bin/env bash
# The "Plan the cluster render" step of preview/action.yml: writes the `steps`
# output for condor-batch from the render step's environment variables.
# The job has no runner environment, so each variable becomes a quoted
# assignment on the command line (gha#1618).
set -euo pipefail
cp "$GITHUB_ACTION_PATH/render-site.sh" .gha-render-site.sh
cp "$GITHUB_ACTION_PATH/../quarto-publish/redirect-stubs.py" .gha-redirect-stubs.py
assign=""
for name in PROJECT_PATH RENDER_PROFILE OUTPUT_DIR FORMATS SKIP_DOCX \
  DOCX_TRACKED_CHANGES TINYTEX HAS_LABEL_PDF HAS_LABEL_DOCX \
  HAS_LABEL_REVEALJS SETUP_JULIA INCREMENTAL_MODE INCREMENTAL_PAGES; do
  assign+=" $name=$(printf '%q' "${!name}")"
done
# A PDF render needs a writable TeX cache under the checkout.
render="mkdir -p \"\$PWD/.texvar\" && env TEXMFVAR=\"\$PWD/.texvar\" TEXMFCACHE=\"\$PWD/.texvar\"$assign REDIRECT_STUBS_SCRIPT=.gha-redirect-stubs.py bash .gha-render-site.sh"
# condor-batch bundles two or more steps; the second one fails the job when
# the render left no output directory.
check="test -d $(printf '%q' "$PROJECT_PATH/$OUTPUT_DIR")"
{
  echo "steps<<GHA_CLUSTER_STEPS"
  echo "$render"
  echo "$check"
  echo "GHA_CLUSTER_STEPS"
} >> "$GITHUB_OUTPUT"
