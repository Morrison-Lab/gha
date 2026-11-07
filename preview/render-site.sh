#!/usr/bin/env bash
# Render the Quarto site for the preview (the "Render Quarto site" step of
# preview/action.yml). The step passes its inputs as environment variables:
# PROJECT_PATH, RENDER_PROFILE, OUTPUT_DIR, FORMATS, SKIP_DOCX,
# DOCX_TRACKED_CHANGES, TINYTEX, HAS_LABEL_PDF, HAS_LABEL_DOCX,
# HAS_LABEL_REVEALJS, SETUP_JULIA, INCREMENTAL_MODE, INCREMENTAL_PAGES and
# REDIRECT_STUBS_SCRIPT. It lives in a file so a later change can run it on a
# cluster node (gha#1563).
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

# Tracked changes compare rendered Word files, so without docx in the
# render that step has nothing to compare (gha#1059). Treat it as a
# `preview:docx` label, which every branch below already honours. An
# explicit `formats` list without docx is left as the caller wrote it.
if [ "$DOCX_TRACKED_CHANGES" = "true" ] && [ "$HAS_LABEL_DOCX" != "true" ]; then
  HAS_LABEL_DOCX=true
  # Say so only where it changes the render.
  case " ${FORMATS:-} " in
    "  ") restored=true ;;
    *" docx "*) restored="$SKIP_DOCX" ;;
    *) restored=false ;;
  esac
  if [ "$restored" = "true" ]; then
    echo "::notice::docx-tracked-changes is on, so the preview renders docx as if labelled preview:docx."
  fi
fi

LOG_FILE="_quarto_preview_render.log"
rm -f "$LOG_FILE"

# A page with `redirect-stub: true` builds html only (gha#1544): a
# profile that leaves such pages out is used for every other format.
STUB_PROFILE=gha-skip-stubs
STUB_PROFILE_FILE="$PROJECT_PATH/_quarto-$STUB_PROFILE.yml"
rm -f "$STUB_PROFILE_FILE"
trap 'rm -f "$STUB_PROFILE_FILE"' EXIT
STUB_COUNT=$(python3 "$REDIRECT_STUBS_SCRIPT" "$PROJECT_PATH" "$STUB_PROFILE" "${RENDER_PROFILE:-}")
set_format_profile() {
  FMT_PROFILE_ARG=("${PROFILE_ARG[@]}")
  if [ "$1" != "html" ] && [ "$STUB_COUNT" != "0" ]; then
    echo "Skipping $STUB_COUNT redirect stub(s) in the $1 render."
    FMT_PROFILE_ARG=(--profile "${RENDER_PROFILE:+$RENDER_PROFILE,}$STUB_PROFILE")
  fi
}

# A render of one page ignores the skip profile's render list, so
# an incremental preview skips a stub's non-html render itself.
skip_stub_target() {
  [ "$2" != "html" ] && [ -f "$1" ] && python3 "$REDIRECT_STUBS_SCRIPT" --is-stub "$1" \
    && echo "Skipping the $2 render of redirect stub $1."
}

# Render one target: the whole project (`first` true cleans the
# output directory) or, for an incremental preview, one page, whose
# render leaves every other output in place (`first` false).
render_target() {
local target="$1" first="$2"
if [ -z "${FORMATS:-}" ]; then
  # Default legacy behavior: derive formats from labels and tinytex input
  FORMAT_LIST=()
  if [ "$TINYTEX" = "true" ] || [ "$HAS_LABEL_PDF" = "true" ]; then
    FORMAT_LIST+=("pdf")
  fi
  if [ "$HAS_LABEL_DOCX" = "true" ]; then
    FORMAT_LIST+=("docx")
  fi
  if [ "$HAS_LABEL_REVEALJS" = "true" ]; then
    FORMAT_LIST+=("revealjs")
  fi
  FORMAT_LIST+=("html")

  for fmt in "${FORMAT_LIST[@]}"; do
    if skip_stub_target "$target" "$fmt"; then continue; fi
    set_format_profile "$fmt"
    if [ "$first" = true ]; then
      quarto render "$target" "${FMT_PROFILE_ARG[@]}" --to "$fmt" --output-dir "$OUTPUT_DIR" 2>&1 | tee -a "$LOG_FILE"
      first=false
    else
      quarto render "$target" "${FMT_PROFILE_ARG[@]}" --to "$fmt" --no-clean --output-dir "$OUTPUT_DIR" 2>&1 | tee -a "$LOG_FILE"
    fi
  done
elif [ "$FORMATS" = "default" ]; then
  # Bare render: let _quarto.yml decide. skip-docx cannot apply here:
  # quarto render --to takes one format, so a comma-joined list such
  # as "html,pdf" fails with "Unknown format", and one invocation per
  # format would prune the other formats' supporting files.
  if [ "$SKIP_DOCX" = "true" ] && [ "$HAS_LABEL_DOCX" != "true" ]; then
    # A plain log line, not an annotation: skip-docx defaults to true, so every
    # caller with formats: default would otherwise fail the annotation gate on a
    # by-design condition (gha#1062).
    echo "skip-docx does not apply to formats: default; rendering every declared format."
  fi
  quarto render "$target" "${PROFILE_ARG[@]}" --output-dir "$OUTPUT_DIR" 2>&1 | tee -a "$LOG_FILE"
else
  # User-specified format list (first format clean, subsequent --no-clean)
  FORMAT_LIST=()
  for word in $FORMATS; do
    if [ "$word" = "docx" ] && [ "$SKIP_DOCX" = "true" ] && [ "$HAS_LABEL_DOCX" != "true" ]; then
      echo "Skipping docx in the preview render (skip-docx)."
      continue
    fi
    FORMAT_LIST+=("$word")
  done

  if [ ${#FORMAT_LIST[@]} -eq 0 ]; then
    echo "::error::formats input was specified but contained no valid format words."
    exit 1
  fi

  for fmt in "${FORMAT_LIST[@]}"; do
    if skip_stub_target "$target" "$fmt"; then continue; fi
    set_format_profile "$fmt"
    if [ "$first" = true ]; then
      quarto render "$target" "${FMT_PROFILE_ARG[@]}" --to "$fmt" --output-dir "$OUTPUT_DIR" 2>&1 | tee -a "$LOG_FILE"
      first=false
    else
      quarto render "$target" "${FMT_PROFILE_ARG[@]}" --to "$fmt" --no-clean --output-dir "$OUTPUT_DIR" 2>&1 | tee -a "$LOG_FILE"
    fi
  done
fi
}

if [ "${INCREMENTAL_MODE:-}" = "incremental" ]; then
  while IFS= read -r page || [ -n "$page" ]; do
    [ -n "$page" ] || continue
    render_target "$PROJECT_PATH/$page" false
  done < "$INCREMENTAL_PAGES"
else
  render_target "$PROJECT_PATH" true
fi
