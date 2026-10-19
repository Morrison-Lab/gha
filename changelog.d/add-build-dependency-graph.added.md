- **New `build-dependency-graph` composite action**
  ([#1125](https://github.com/Morrison-Lab/gha/issues/1125)).
  It parses a Quarto notes site's definition and result divs.
  It builds the graph of which div uses which from the `@id` and link references inside each div.
  It writes `dependency-graph.json`.
  It ships `dependency-graph.js`, which draws each div's prerequisites and postrequisites as an SVG.
  It warns about cycles and forward references.
  Piloted in `Morrison-Lab/lds`.
