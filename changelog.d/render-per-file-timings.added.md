- **`quarto-publish` logs how long each per-file render takes.**
  With `per-file-formats`, every `quarto render FILE --to FORMAT` now logs its
  elapsed seconds, and the step ends with a table of the total time and file
  count per format and the 25 slowest renders, also appended to the job summary.
  A site whose publish runs for two hours can now see which pages and formats
  take the time (gha#1420).
