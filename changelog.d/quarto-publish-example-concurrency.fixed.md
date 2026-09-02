- **`examples/quarto-publish.yml` and `examples/report-failure.yml` no
  longer name their concurrency group `gh-pages`** (#809).
  `quarto-publish.yml`'s deploy job has declared that group itself since
  #654, and a caller-level block with the same name deadlocks the run with
  no runner, no steps, and no log, so consumers who copied the stub stopped
  publishing silently.
  Both stubs keep a concurrency block, renamed to
  `quarto-publish-${{ github.ref }}`, rather than losing one -- the same
  renamed-group convention `examples/r-cmd-check.yml` and
  `examples/spellcheck.yml` already use.
  Note the rename narrows what is serialized, and is not equivalent to the
  old block: `gh-pages` at caller level serialized this workflow against
  *every other* gh-pages workflow in the repo, where the new group
  serializes it only against workflows sharing that name, per ref.
  The two stubs deliberately share it, since `report-failure.yml` documents
  itself as a job to merge into an existing caller rather than a second
  workflow to install alongside the first.
  The gh-pages branch is still protected, by the callee deploy jobs that
  continue to share the `gh-pages` group; what can now overlap is one
  workflow's render phase with another's deploy.
  Those two stubs, the `altdoc-multiversion-docs`, `preview-deploy` and
  `cleanup-pr-previews` stubs, the reference pages, and the README now say
  not to reuse the `gh-pages` name, and a new
  `audit_example_concurrency.py` check in `_selftest.yml` fails when any
  example stub declares a group that the workflow it calls also declares.
  The audit checks both placements on each side: a caller's top-level block
  and one on the calling job itself, against a callee's job-level groups and
  its own top-level one.
