- **`examples/quarto-publish.yml` and `examples/report-failure.yml` no
  longer declare a top-level `gh-pages` concurrency group** (#809).
  `quarto-publish.yml`'s deploy job has declared that group itself since
  #654, and a caller-level block with the same name deadlocks the run with
  no runner, no steps, and no log, so consumers who copied the stub stopped
  publishing silently.
  The stubs, the `preview-deploy` and `cleanup-pr-previews` stubs, the
  reference pages, and the README now say not to declare it, and a new
  `audit_example_concurrency.py` check in `_selftest.yml` fails when any
  example stub's top-level group is also declared on a job of the workflow
  it calls.
