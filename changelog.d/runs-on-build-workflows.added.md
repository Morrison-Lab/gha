- **`preview.yml`, `preview-deploy.yml` and `quarto-publish.yml`** --
  accept a `runs-on` input (default `ubuntu-latest`),
  so a private repository can build and publish its site
  on a self-hosted runner while GitHub-hosted minutes are unavailable
  ([#1167](https://github.com/Morrison-Lab/gha/issues/1167)).
