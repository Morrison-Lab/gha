- **`check-merge-drops` no longer reports a line the merge kept a longer
  version of.**
  When one side added an item to a list line and the other side's line
  already had that item plus another, keeping the longer line lost nothing,
  yet the check failed the PR, because the longer line came from a parent
  and not from the resolution.
  A line of four or more words is now not a drop when another parent
  rewrote it at the same place in the file by inserting one run of words.
  The longer line must come from a diff hunk that overlaps or adjoins the
  dropped line's hunk, and the inserted run must hold no negation such as
  `not`
  (Morrison-Lab/lds#2863, a private repository the link checker cannot reach).
