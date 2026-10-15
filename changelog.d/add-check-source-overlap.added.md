- **New `check-source-overlap` capability**.
  Flags paragraphs of Markdown and Quarto prose that copy a reference text,
  as a guard against unintentional plagiarism by authors and AI agents alike.
  It extracts text from PDFs named by `corpus-files` in a private corpus repository
  (default `Morrison-Lab/mlr`, read with the `corpus-token` secret)
  and compares each added paragraph by word 6-grams:
  a long verbatim run or a high share of shared 6-grams flags it.
  Code, math, tables, citations, quotations and blockquotes are skipped,
  `<!-- overlap-ok: reason -->` exempts a passage checked by hand,
  and a run with no corpus or no input exits 2 instead of passing.
  The extracted text stays in the runner's temporary directory.
  The same `check_source_overlap.py` runs locally for agents before they push.
