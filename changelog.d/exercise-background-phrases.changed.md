- `check-exercise-background` judges only a run of title words that matches a whole defined term (so "times" is no longer read as part of "time series"),
  splits a definition title at "also called" so each alias is a term,
  counts the word a math macro says, so `\grad` says gradient,
  counts the words inside `\text{}`, `\operatorname{}`, and `\mathrm{}`,
  and treats "expand" as a task verb (gha#1481).
