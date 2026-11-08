- **`check-fragments` input on `check-quarto-links`**, default off.
  When on, a relative link to a `.qmd`, `.md` or `.Rmd` page must also name an id
  the page defines (include files expanded), so an anchor that moved to another page
  is reported instead of passing as a link to a page that still exists
  ([gha#1675](https://github.com/Morrison-Lab/gha/issues/1675)).
