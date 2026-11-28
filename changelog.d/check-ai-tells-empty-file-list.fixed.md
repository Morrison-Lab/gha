- `check-ai-tells` no longer crashes with "invalid 'file' argument" when it finds no Markdown or Quarto file to scan.
  An empty list reached `file.exists(NULL)` before the empty-list check could run.
  A whole-tree search that finds nothing while git tracks such files in the directory now fails with an error naming the directory and the tracked count,
  because the working tree is incomplete and nothing was scanned.
  A directory with no such files still passes with a notice.
- A file the whole-tree search finds, such as `notes[1].md`, is now scanned as a literal name.
  It used to be re-expanded as a glob, which matched nothing, so the file went unscanned.
