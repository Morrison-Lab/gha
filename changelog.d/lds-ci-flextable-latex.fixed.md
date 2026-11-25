- **`flextable`, `colortbl`, `multirow`, `ulem`, and `wrapfig` in the `lds-ci.sif` definition.**
  Once lds rendered its data previews with `gtsummary::as_flex_table()`,
  every cluster publish failed the PDF pass on `multirow.sty`,
  which Quarto could not install into the read-only `/opt/TinyTeX`
  (Morrison-Lab/lds#3193).
  flextable's LaTeX output also loads `colortbl`, `ulem`, and `wrapfig`,
  which the image lacked, so all four are installed,
  and `%test` now checks that each `.sty` file and the R package are present.
