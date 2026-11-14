- `preview` and `quarto-publish` now spread cluster renders over the CI cluster heads by default, instead of sending every job to cse-head.
  An empty `cluster-head` (the new default) uses cse-head and csci-head.
  It adds the csci-lab desktop pool on port 922 when `cluster-image-file` is set, because that pool has no cluster home to read `cluster-image` from.
  A caller that passes `cluster-head` keeps its own list ([gha#1518](https://github.com/Morrison-Lab/gha/issues/1518)).
