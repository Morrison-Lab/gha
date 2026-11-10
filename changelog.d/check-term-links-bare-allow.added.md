- **`bare-allow` finding in `check-term-links`**:
  an opt-out pragma on an added line must now give a reason,
  `<!-- check-term-links: allow: <reason> -->`;
  the reasonless form still suppresses the line but is reported
  ([gha#1772](https://github.com/Morrison-Lab/gha/issues/1772)).
