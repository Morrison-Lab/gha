- `check-pr-size` caps a PR at 40 files and 1200 lines by default, double the old 20 and 600 (Ezra, 2026-11-28: "double the cap on pr size").
  A line moved unchanged between files no longer counts, nor does a file whose every changed line moved,
  so a pure movement PR passes at any size without the "mechanical, content-identical" phrase,
  as ai-config's `no-oversized-pr-push` hook already measured it.
