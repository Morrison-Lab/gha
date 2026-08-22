- `ai-code-review`: two fail-open branches in the candidate loop are closed
  (#362).
  A run whose id could not be located within the poll window now falls through
  to the next candidate instead of exiting `0`.
  A poll that could not find its own run has learned nothing about whether the
  review happened, so that was the branch where the least was known.
  Note the trade this makes, since it is a real behaviour change rather than a
  pure tightening: the dispatch itself had already succeeded, so falling
  through can start a second agent's review while the first one's run is still
  queued.
  That risks a duplicate paid review, and on workflows sharing a per-PR
  `cancel-in-progress` group it can cancel the review it was looking for.
  The previous `exit 0` avoided that by trusting an unconfirmed dispatch, which
  is the failure this issue is about.

- `ai-code-review`: the run-location poll now takes the oldest run created at
  or after its own dispatch rather than the newest.
  `gh run list` returns newest-first, so a second dispatch landing inside the
  poll window handed back the wrong run, and the loop then watched and reported
  on a run it had not started.
