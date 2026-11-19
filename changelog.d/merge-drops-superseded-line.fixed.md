- **`check-merge-drops` no longer reports a line the merge kept a longer
  version of.**
  When one side added an item to a list line and the other side's line
  already had that item plus another, keeping the longer line lost nothing,
  yet the check failed the PR.
  A line of four or more words is now not a drop when another parent's hunk
  at the same place added it with one run of words inserted, and that run
  holds no negation
  (Morrison-Lab/lds#2863, a private repository the link checker cannot reach).
