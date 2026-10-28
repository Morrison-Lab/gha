- `check-solution-citations`:
  a `proof` div whose whole body is one line with one `@sol-` citation no longer needs the allow marker
  ([#1251](https://github.com/Morrison-Lab/gha/issues/1251)).
  A proof with its own steps, display math, a code fence, a nested div or a second citation is still flagged,
  and so is a citation inside a result div.
