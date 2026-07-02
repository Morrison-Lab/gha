- **`claude-code-review.yml`'s reviewer no longer derails on a denied tool
  call** (#185). The action's default agent-mode `allowedTools` has no
  network-fetch tools (`WebFetch`/`WebSearch`), but the review prompt's own
  fact-checking and hallucination-detection instructions can lead the agent
  to attempt one anyway — e.g. reviewing a diff that discusses fetching an
  external URL. The resulting permission denial sometimes ended the run with
  no `### Verdict`, which `check-review-execution.sh`'s guard (#172/#176)
  correctly fails as a stub review, red-X'ing `require-review` for a PR that
  was never actually reviewed (reproduced 3/3 times on #180, all with an
  identical `permission_denials_count: 1` / `num_turns: 4` fingerprint). The
  reviewer's system prompt now states up front that network-fetch tools
  aren't available (so it verifies from the repo and its own knowledge
  instead of attempting the fetch) and that a denied tool call is never a
  reason to stop early — it must still finish with its findings and the
  explicit verdict line.
