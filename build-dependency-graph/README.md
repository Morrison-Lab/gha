# build-dependency-graph

Graphs of definitions and results by prerequisite and postrequisite.
An edge from A to B means A uses B, so B is a prerequisite of A and A is a postrequisite of B.
Edges come from the `@id`, `page.qmd#id` and cross-site links already inside each `#def-`, `#thm-`, `#lem-`, `#prp-` and `#cor-` div.
No hand-written tags are needed.
Lean `leanblueprint` and KnowTeX build the same kind of graph from hand-written `\uses` tags.

## Use in a Quarto website

1. Run the action before the render.
   It writes into `chapters/` by default.

   ```yaml
   - uses: Morrison-Lab/gha/build-dependency-graph@v3
   ```

   For local renders, vendor `build_dependency_graph.py` and run it as a `pre-render` step, as `Morrison-Lab/lds` does.

2. List `chapters/dependency-graph.js` and `chapters/dependency-graph.json` under `resources:`.

3. Add `- text: '<script src="dependency-graph.js" defer></script>'` to the HTML format's `include-after-body` list.

Every definition and result div then ends with a "Dependencies" block, folded by default.
It holds one graph focused on that div, read top to bottom: prerequisites above, postrequisites below, two levels each way.
Each box takes the color of its div type, matching the notes' div colors.

Optional: an element with id `dependency-graph-page` gets one more folded block, a graph of every definition and result on that page.
The script prints cycles and forward references.
A forward reference is a div that uses one defined later on its page.
