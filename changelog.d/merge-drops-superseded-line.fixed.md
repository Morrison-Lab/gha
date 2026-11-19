- **`check-merge-drops` no longer reports a line the merge kept a longer
  version of.**
  When one side added an item to a list line and the other side's line
  already had that item plus another, keeping the longer line lost nothing,
  yet the check failed the PR, because the longer line came from a parent
  and not from the resolution.
  A line of four or more words is now not a drop when the merge kept a
  longer line in the same file that holds every one of its words, in order.
  That longer line must come from another parent's additions to the file,
  or from the resolution itself
  (Morrison-Lab/lds#2863, a private repository the link checker cannot reach).
