- `annotation-gate` allows the git transport errors of a checkout fetch
  that `actions/checkout` retried (`early EOF`, `RPC failed; curl 55`,
  `fetch-pack: invalid index-pack output`, and their siblings)
  in its default allow list,
  so a job that passed on the retry no longer fails the gate (gha#1731).
