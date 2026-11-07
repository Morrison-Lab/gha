- **`luacolor`, `needspace`, `parskip`, and `titling` in the `lds-ci.sif` definition.**
  A full-site `quarto render --profile website` on the cluster image failed
  at the `regularization.qmd` PDF render, because `luacolor.sty` was missing
  and Quarto could not install it into the read-only `/opt/TinyTeX`
  ([gha#1431](https://github.com/Morrison-Lab/gha/issues/1431)).
  The other three are LaTeX packages the lds sources load that the image's
  TinyTeX lacks (compared against the installed list from the same image).
