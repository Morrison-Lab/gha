- `check-exercise-ends-with-task`:
  A one-line display equation followed by an attribute block, such as `$$x = 1$$ {#eq-a}`, or by any other text, now closes on its own line (gha#1908).
  Before, the check read it as an opening `$$` and skipped the rest of the exercise,
  so a figure, table, or include after it was never reported.
