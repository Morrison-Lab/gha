- `check-pr-size` no longer counts a path that `.gitattributes` marks `linguist-generated`,
  so a repo marks its committed generator outputs once and a small change to their input stays under the cap
  ([gha#1959](https://github.com/Morrison-Lab/gha/issues/1959)).
