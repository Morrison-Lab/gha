- **`check-merge-drops` no longer reports a line the merge kept a longer
  version of.**
  When one side added an item to a list line and the other side's line
  already had that item plus another, keeping the longer line lost nothing,
  yet the check failed the PR, because the longer line came from a parent
  and not from the resolution.
  A line is now not a drop when a longer line of the merge's copy of the same
  file holds every one of its words, in order
  (Morrison-Lab/lds#2863, a private repository the link checker cannot reach).
