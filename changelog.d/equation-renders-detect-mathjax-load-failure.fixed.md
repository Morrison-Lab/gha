- **`check-equation-renders` no longer silently passes when MathJax itself
  fails to load** (#230). MathJax is loaded from a CDN at runtime rather than
  vendored, so a transient network hiccup or blocked host could keep it from
  ever initializing on a page that references it -- previously, this made the
  DOM scan find zero error nodes (since MathJax never ran), which read as "no
  equation render errors found" even though nothing was actually verified.
  The composite now tracks whether a page references a MathJax script and
  whether it became ready within the timeout, reporting a load failure as its
  own error alongside genuine equation errors.
