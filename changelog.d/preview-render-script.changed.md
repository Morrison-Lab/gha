- `preview` runs its "Render Quarto site" step from `preview/render-site.sh` instead of an inline script.
  The render is unchanged.
  The file lets a later change run the render on a cluster node (gha#1563).
