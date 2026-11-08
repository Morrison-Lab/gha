#!/usr/bin/env bash
# check-one-function-per-file: allow-multiple
# The "Render Quarto project" step of quarto-publish/action.yml passes its
# inputs in the environment. It is a file so a cluster job can run it (gha#1563).
set -euo pipefail
# See "Set up JuliaCall and its Julia dependencies" for why.
if [ "$SETUP_JULIA" = "true" ] && command -v R >/dev/null 2>&1; then
  R_LD_LIBRARY_PATH="$(R RHOME)/lib"
  export R_LD_LIBRARY_PATH
fi
PROFILE_ARG=()
if [ -n "${RENDER_PROFILE:-}" ]; then
  PROFILE_ARG=(--profile "$RENDER_PROFILE")
fi

# Parse formats (whitespace-separated)
FORMAT_LIST=()
for word in ${FORMATS:-}; do
  FORMAT_LIST+=("$word")
done

LOG_FILE=$(mktemp)

if [ ${#FORMAT_LIST[@]} -eq 0 ]; then
  # Single render invocation
  quarto render "$PROJECT_PATH" "${PROFILE_ARG[@]}" --output-dir "$OUTPUT_DIR" 2>&1 | tee "$LOG_FILE"
else
  # Per-format split render. Each later render deletes the `site_libs`
  # files its own format does not use, which left the HTML pages with
  # no CSS or JavaScript (mds). Collect every format's files as it is
  # written, and put the union back once all renders are done.
  SITE_LIBS="$PROJECT_PATH/$OUTPUT_DIR/site_libs"
  SITE_LIBS_STAGE=$(mktemp -d)
  first=true
  STUB_PROFILE=gha-skip-stubs
  STUB_PROFILE_FILE="$PROJECT_PATH/_quarto-$STUB_PROFILE.yml"
  rm -f "$STUB_PROFILE_FILE"
  trap 'rm -f "$STUB_PROFILE_FILE"' EXIT
  STUB_COUNT=$(python3 "$REDIRECT_STUBS_SCRIPT" "$PROJECT_PATH" "$STUB_PROFILE" "${RENDER_PROFILE:-}")
  for fmt in "${FORMAT_LIST[@]}"; do
    # A page with `redirect-stub: true` builds html only (gha#1544):
    # leave it out of every other format's render.
    FMT_PROFILE_ARG=("${PROFILE_ARG[@]}")
    if [ "$fmt" != "html" ] && [ "$STUB_COUNT" != "0" ]; then
      echo "Skipping $STUB_COUNT redirect stub(s) in the $fmt render."
      FMT_PROFILE_ARG=(--profile "${RENDER_PROFILE:+$RENDER_PROFILE,}$STUB_PROFILE")
    fi
    if [ "$first" = true ]; then
      quarto render "$PROJECT_PATH" "${FMT_PROFILE_ARG[@]}" --output-dir "$OUTPUT_DIR" --to "$fmt" 2>&1 | tee "$LOG_FILE"
      first=false
    else
      quarto render "$PROJECT_PATH" "${FMT_PROFILE_ARG[@]}" --output-dir "$OUTPUT_DIR" --to "$fmt" --no-clean 2>&1 | tee -a "$LOG_FILE"
    fi
    if [ -d "$SITE_LIBS" ]; then
      cp -a "$SITE_LIBS/." "$SITE_LIBS_STAGE/"
    fi
  done
  mkdir -p "$SITE_LIBS"
  cp -a "$SITE_LIBS_STAGE/." "$SITE_LIBS/"
fi

if [ -n "${PER_FILE_FORMATS:-}" ]; then
  # Word-split on purpose: the formats are whitespace-separated.
  # shellcheck disable=SC2086
  QUARTO_PROFILE="${RENDER_PROFILE:-}" python3 "$PER_FILE_SCRIPT" "$PROJECT_PATH" "$OUTPUT_DIR" $PER_FILE_FORMATS 2>&1 | tee -a "$LOG_FILE"
fi

if [ "$FAIL_ON_WARN" = "true" ]; then
  if grep -iE '(^|[[:space:]])WARN([[:space:]:]|$)|Warning:' "$LOG_FILE"; then
    echo "::error::Quarto emitted one or more render warnings and fail-on-render-warning is enabled."
    exit 1
  fi
fi

if [ -n "${FORBID_PATTERNS:-}" ]; then
  while IFS= read -r pattern || [ -n "$pattern" ]; do
    trimmed_pattern=$(echo "$pattern" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
    if [ -n "$trimmed_pattern" ]; then
      if grep -F "$trimmed_pattern" "$LOG_FILE"; then
        echo "::error::Quarto render log contains forbidden pattern '$trimmed_pattern'."
        exit 1
      fi
    fi
  done <<< "$FORBID_PATTERNS"
fi
