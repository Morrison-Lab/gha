- `claude-code-review.yml`: a review the model emits across several
  assistant blocks is now posted whole (#710).
  The posted comment used to be only the LAST verdict-bearing block,
  so a review whose follow-up restated the verdict posted just that
  tail -- a comment opening mid-argument and referencing analysis it
  never included.
  The extraction now posts the span from the first verdict-bearing
  block through the last, blocks between included;
  single-block reviews are unchanged.
