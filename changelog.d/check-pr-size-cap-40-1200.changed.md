- `check-pr-size` doubles its default caps (Ezra, 2026-11-28: "double the cap on pr size").
  A PR may now change up to 40 files and up to 1200 lines.
  A line moved unchanged between files no longer counts, nor does a file whose every changed line moved.
  So a pure movement PR passes at any size without the "mechanical, content-identical" phrase,
  as ai-config's `no-oversized-pr-push` hook already measured it.
