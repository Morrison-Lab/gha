- `preview` no longer emits a `::notice::` when `skip-docx` is true with `formats: default`.
  That is by design, and the notice made the annotation gate fail every such caller.
  The message is now a plain log line.
