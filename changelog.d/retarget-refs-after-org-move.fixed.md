- **Every `uses:` reference now points at `Morrison-Lab/gha`** instead of
  `d-morrison/gha`, which stopped resolving after the repository moved to the
  `Morrison-Lab` organization.
  Actions does not follow a repository-transfer redirect when resolving a
  reusable workflow, so a caller on the old path fails at run startup with
  `workflow was not found` before any job is scheduled.

  This covers the reusable workflows' own internal references, the caller
  stubs under `examples/`, and the copy-paste examples in `README.md` and the
  reference pages.
  Major tags are unchanged -- a `@v1` reference stays `@v1`, and `@v2` stays
  `@v2`.

  **Consumers must update their own callers.** This release fixes the
  references inside this repository; a consumer repo whose
  `.github/workflows/` still says `d-morrison/gha` is broken until it is
  changed to `Morrison-Lab/gha`.
