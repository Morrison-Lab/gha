### Fixed

- Replaced interval quantifier regex `{1,6}` in `strip-non-invoking-markup.sh` ATX heading check with a portable `match()` length check to prevent `mawk 1.3.4` regex compilation panics (#448, #451).
- Updated `detect-review-request.sh` body normalization to evaluate `strip-non-invoking-markup.sh` outside `if` conditions, ensuring stripper failures abort loudly under `set -e` rather than silently returning `false`.
