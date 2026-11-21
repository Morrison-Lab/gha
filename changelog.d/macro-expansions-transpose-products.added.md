- `check-macro-expansions` now flags hand-written transpose products:
  self outer products (`\vX \tp{\vX}` for `\soprod`), outer products (`\oprod`),
  cross products (`\tp{\va} \vX` for `\tprod` or `\ccprod`),
  Gram matrices (`\tp{\mX} \mX` for `\stprod`),
  and quadratic and bilinear forms whose factors are macro calls
  (`\tp{\vc} \inv{\mS} \vc` for `\qform`).
  These bodies have three tokens, below the four-token floor, so the check missed them
  (Ezra, 2026-11-20, on Morrison-Lab/pds#478).
  A product's argument may now be a macro applied to one braced group, with a subscript and superscript.
  A number, `\tp`, and text, spacing, environment, and delimiter commands are never arguments,
  and a product that opens on a factor is not reported in the middle of a longer product.
  An argument macro is no longer split into two (`\vX` read as `\v` and `X`),
  which removes false findings such as `\grad_{\vx}\, p` reported as `\gradwrt`.
  Measured over the whole tree on 2026-11-20: pds goes from 94 findings to 83 and lds from 943 to 829;
  the new findings are products, and most of the dropped ones were spurious `\bform` matches against `\text`.
