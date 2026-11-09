- **`lua-ul`, `hyperxmp`, `latex-lab`, `luamml`, `mathtools`, `pdfmanagement`, and `tagpdf` in the `lds-ci.sif` definition.**
  After `luacolor` was added, the next full-site render on the cluster image
  failed at the same PDF step on `lua-ul.sty`, which Quarto could not install
  into the read-only `/opt/TinyTeX`
  ([gha#1431](https://github.com/Morrison-Lab/gha/issues/1431)).
  The other six are packages that the working TinyTeX on cf463-02 has and the
  image lacks; they belong to the same PDF toolchain.
