- **`strip-non-invoking-markup.sh` ATX heading regex now uses a portable `match()` length check**,
  preventing `mawk 1.3.4` regex compilation panics (#448, #451).
  Also updates `detect-review-request.sh` body normalization to evaluate
  `strip-non-invoking-markup.sh` outside `if` conditions so script failures propagate
  a non-zero exit under `set -e`, and adds `continue-on-error: true` to `claude.yml`'s
  primary detection step so workflow runs tolerate stripper/engine failures safely.

