- **New `build-dependency-graph` composite action**
  ([#1125](https://github.com/Morrison-Lab/gha/issues/1125)).
  Parses a Quarto notes site's definition and result divs, builds the graph of
  which uses which from the `@id` and link references inside each div, and
  writes `dependency-graph.json`; ships `dependency-graph.js`, which draws each
  div's prerequisites and postrequisites as an SVG. Warns about cycles and
  forward references. Piloted in `Morrison-Lab/lds`.
