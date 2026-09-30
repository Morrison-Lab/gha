- **New `update-quarto-extensions.yml` reusable workflow** (#985). Updates
  vendored Quarto extensions in-place to upstream semantic version tags and
  opens a pull request when newer versions are available. Scans `_extensions/`
  to discover vendored extensions, resolves their source repositories via
  configurable mappings (with defaults for common extensions), preserves local
  directory layouts, checks for uncommitted local modifications, and opens or
  updates an automated pull request with release notes. Accompanied by the
  `update-quarto-extensions` composite action and offline test suite.
