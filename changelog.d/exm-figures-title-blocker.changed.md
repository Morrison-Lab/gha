- **`check-exm-figures` also flags a block ahead of a div's title heading**
  ([#1567](https://github.com/Morrison-Lab/gha/issues/1567)).
  Quarto reads a level 4 or deeper heading as a crossref div's title only when it is the div's first block,
  so an HTML comment ahead of it makes the title a section heading with its own anchor.
  The check applies to every `#def-`, `#thm-`, `#lem-`, `#prp-`, `#cor-`, `#cnj-`, `#exm-`, `#exr-`, and `#rem-` div the diff touches,
  and it shares the check's `fail`, `whole-tree`, and `paths-ignore` inputs.
  A whole-tree run finds seven such divs in lds and five in mds.
