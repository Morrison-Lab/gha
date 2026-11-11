- `check-term-links`:
  prose outside divs now runs from one heading to the next, as psw's linking rule defines a passage, instead of ending at every blank line (gha#1283).
  A term linked once in a section is not a first use again in a later paragraph of that section.
  A div keeps its own scope and does not split the prose around it, and a heading inside a div does not start a new section.
  The issue reports 204 whole-tree findings on psw under the old rule and 151 under this one.
