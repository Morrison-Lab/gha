- `annotation-gate` allows the warnings `check-links` demotes a link to when its host did not answer or sent a 5xx on a line the change does not add.
  gha#2121 made those links non-blocking, but every gated repository still failed on them through the gate (mds#863, pds#475, sds#643 and mcs#198 on 2026-11-20).
  The same link on a line the change adds still fails.
