- **`per-file-formats` input on `quarto-publish.yml` and the `quarto-publish`
  composite.**
  It renders the listed formats (for example `pdf`) one file at a time, each in
  its own `quarto render FILE --to FORMAT` process, after the normal render.
  A single process over a large project grows until Deno hits its heap cap, which
  stopped the `Morrison-Lab/mds` publish with `Fatal JavaScript out of memory`
  in the PDF pass.
  A caller lists its other formats in `formats` and the large one here.
  The default is empty, so existing callers are unchanged
  ([gha#1170](https://github.com/Morrison-Lab/gha/issues/1170)).
