- **`examples/quarto-publish.yml` and `examples/report-failure.yml` no
  longer name their concurrency group `gh-pages`** (#809).
  `quarto-publish.yml`'s deploy job has declared that group itself since
  #654, and a caller-level block with the same name deadlocks the run with
  no runner, no steps, and no log, so consumers who copied the stub stopped
  publishing silently.
  Both stubs keep a concurrency block, renamed to
  `quarto-publish-${{ github.ref }}`, so a consumer still gets the
  run-level serialization the original block was there to provide -- the
  same renamed-group convention `examples/r-cmd-check.yml` and
  `examples/spellcheck.yml` already use.
  Those two stubs, the `altdoc-multiversion-docs`, `preview-deploy` and
  `cleanup-pr-previews` stubs, the reference pages, and the README now say
  not to reuse the `gh-pages` name, and a new
  `audit_example_concurrency.py` check in `_selftest.yml` fails when any
  example stub declares a group that a job of the workflow it calls also
  declares.
  The audit checks both caller-level placements -- a top-level block, and
  one on the calling job itself, which is valid YAML on a job that `uses:`
  a reusable workflow and deadlocks identically.
