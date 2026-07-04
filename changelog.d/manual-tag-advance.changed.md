- **Major-version tags no longer slide automatically on every push to `main`**
  (#225). `slide-major-tag.yml` now runs only on `workflow_dispatch`, so
  advancing `@v1`/`@v2` to a new `main` commit is a deliberate action taken
  once a change has been validated -- optionally against a canary consumer
  pinned to `@main`, a specific commit SHA, or a feature branch first --
  rather than an automatic side effect of every merge. See the README's
  "Advancing a major tag" section for the new procedure.
