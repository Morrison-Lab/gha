- **`partial-link` in `check-term-links` now also fires on a link followed by another word of its target's title**:
  `[probability](...#def-pdf) density` is flagged when the target
  is titled "Probability density function", even if "probability density"
  is not itself a defined term
  ([gha#1787](https://github.com/Morrison-Lab/gha/issues/1787)).
