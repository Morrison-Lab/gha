- **`stale-allow` finding in `check-term-links`**:
  an opt-out pragma on an added line that suppresses no finding is reported,
  so a defensive or leftover `<!-- check-term-links: allow -->` is deleted
  instead of accumulating
  ([gha#1771](https://github.com/Morrison-Lab/gha/issues/1771)).
