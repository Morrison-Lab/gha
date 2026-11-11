- `check-exercise-ends-with-task`:
  a paragraph that opens in lowercase right after a display equation, such as "where $x$ is ...", now continues the sentence the display interrupted (gha#1843).
  It is judged together with the paragraph before the display, so an exercise whose task sentence runs on past its equation is no longer reported.
  A capitalised paragraph, or any block between the paragraph, the display and the follower, still starts a new sentence.
  A solution or callout div counts as such a block, though it is not judged,
  and a sentence inside a list item never runs on to a paragraph after the list.
