- **`preview` saves the Quarto freeze cache even when the build fails or is cancelled** (#1184).
  A render stopped by its time limit or a newer push used to discard every page it had finished.
  The next run now resumes from those pages instead of executing them again.
