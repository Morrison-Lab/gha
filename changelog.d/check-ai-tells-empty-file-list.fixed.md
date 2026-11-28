- `check-ai-tells` no longer crashes with "invalid 'file' argument" when it finds no Markdown or Quarto file to scan.
  An empty list reached `file.exists(NULL)` before the empty-list notice could run.
  The notice now names the directory it searched, so a run in the wrong working directory is visible in the log.
