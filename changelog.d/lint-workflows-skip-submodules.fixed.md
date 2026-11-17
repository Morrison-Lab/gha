- `lint-workflows` no longer audits a submodule's workflows with zizmor.
  In a repository with a `.gitmodules` file it passes zizmor only the workflows and actions git tracks,
  so a submodule left checked out on a reused self-hosted workspace cannot fail the caller's lint (gha#2079).
