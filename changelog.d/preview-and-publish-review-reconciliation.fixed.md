- Reconcile review findings across preview and quarto-publish composite actions and documentation:
  - Forward output-dir to quarto render across all render steps in preview composite action.
  - Guard Install R dependencies step in preview on non-empty 
-packages.
  - Fix PR metadata filenames and action value written by preview for preview-deploy and check-equation-renders compatibility.
  - Update README.md and website/workflows.qmd key inputs tables for quarto-publish.yml, preview.yml, and preview-deploy.yml.
  - Add automated selftest coverage for quarto-publish with ormats and render-warning checks.
