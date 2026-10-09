- **`student-qmd`'s `prune-macros` check no longer fails on a document with a table.**
  Taking the macro definitions out of the parsed document dropped every JSON
  null in a list, including a table's empty short caption, so Pandoc refused
  the result.
  Only a raw TeX block the definitions left empty is dropped now.

- **`prune-macros` keeps the macros the answers use.**
  It counted only the student file, so a macro used only inside an
  answer-key-only div lost its definition.
  It now counts the whole source, answers included, so a student writing an
  answer has the answer key's notation.
  A definition that only an answer uses therefore reaches the student file as
  written, as every definition did with `prune-macros` off.
