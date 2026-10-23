- **`check-*` and `lint-*` workflows: `runs-on` input** --
  38 reusable workflows that take no secrets now accept a `runs-on` input
  (default `ubuntu-latest`, so every existing caller is unchanged),
  so a private repository can run them on a self-hosted runner
  while GitHub-hosted minutes are unavailable.
  Never point a public repository at a self-hosted runner
  ([#1167](https://github.com/Morrison-Lab/gha/issues/1167)).
