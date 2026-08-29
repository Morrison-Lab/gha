- **New `versioning-docs` selftest check catches @v1/@v2 documentation
  drift automatically** (#730). Every capability that ships past the frozen
  `@v1` snapshot has to be named in several hand-restated versioning-list
  regions (README.md, `website/versioning.qmd`, `website/workflows.qmd`,
  and `CLAUDE.md`), and that restatement has drifted four separate times
  (gha#181, gha#374, gha#728 rounds 1 and 2) because every prior fix only
  checked the lists against each other. `audit_capability_versioning_docs.py`
  derives ground truth from `.github/workflows/*.yml` file existence and
  each capability's own `examples/*.yml` self-reference instead, and runs
  in CI on every PR. Running it against this repo's own tree at PR time
  found (and this PR fixes) four capabilities missing from README's main
  `## Versioning` paragraph and one missing from its
  `### Pinning third-party actions` subsection.
