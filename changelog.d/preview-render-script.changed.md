- `preview` runs its "Render Quarto site" step from `preview/render-site.sh` instead of an inline script, with the render unchanged.
  The file lets a later change run the render on a cluster node (gha#1563).
