- **`strip-non-invoking-markup.sh` ATX heading regex now uses a portable `match()` length check**,
  preventing `mawk 1.3.4` regex compilation panics (#448, #451).
  Also updates `detect-review-request.sh` body normalization to evaluate
  `strip-non-invoking-markup.sh` outside `if` conditions, ensuring stripper failures
  abort loudly under `set -e` rather than silently returning `false`.
