- `claude.yml`, `gemini.yml`, `small-model-agent.yml`, and `altdoc-multiversion-docs.yml` install Quarto through the internal `install-quarto` composite (gha#1678, gha#1846).
  A runner that sees the group-share release cache reads the pinned Quarto 1.11.9 from it, with TinyTeX where the step asked for it.
  Any other runner falls back to `quarto-dev/quarto-actions/setup` as before.
  These four used to take the setup action's default, the latest Quarto release.
  They now get the pinned version, the same as every other caller of `install-quarto`.
