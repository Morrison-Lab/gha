- Docs: CLAUDE.md's "Standing tag-slide policy" section now requires that
  no review this session requested or is waiting on for the PRs that introduced
  those commits is still pending.
  Check runs alone miss reviews that are not check runs,
  such as an independent adversarial review a session dispatched and is waiting on,
  so hold the slide until any requested review returns clean
  ([#977](https://github.com/Morrison-Lab/gha/issues/977)).
