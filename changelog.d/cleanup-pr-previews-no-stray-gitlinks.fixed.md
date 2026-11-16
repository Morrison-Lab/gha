- `cleanup-pr-previews` no longer publishes untracked files left in a reused self-hosted workdir.
  It staged with `git add -A`, so a `latex-macros` submodule left by an earlier `main` checkout landed on `gh-pages` as a gitlink with no `.gitmodules` entry,
  and the checkout's post-job step then failed with git exit code 128 (the lds `annotation-gate` failure of 2026-11-15).
  It now stages only changes to tracked files, and drops any gitlink already on `gh-pages`.
