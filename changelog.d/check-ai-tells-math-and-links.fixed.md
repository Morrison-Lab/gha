- **`check-ai-tells` no longer reads math, macro names or link targets as prose**.
  Its inline-math pattern put a backslash inside a `[^...]` class,
  which a non-perl regex reads literally,
  so a span such as `$\leverage{i}$` was never stripped and its macro name was flagged.
  Inline math now follows Pandoc's rule (so currency is left alone),
  `$$...$$` is stripped on one line or across lines,
  a link target and a `{#id}` attribute block are dropped so only link text is prose,
  and a bare `\leverage` macro name is exempt
  ([gha#1359](https://github.com/Morrison-Lab/gha/issues/1359)).
