- **New `check-secrets` capability** (composite action +
  `check-secrets.yml` reusable workflow) (#384).
  Scans the caller's git **history** for committed credentials -- API tokens,
  private keys, high-entropy password assignments -- using
  [gitleaks](https://github.com/gitleaks/gitleaks) (MIT),
  whose release binary is pinned by version and verified against a pinned
  SHA-256 of the release's own checksums file.
  `check-phi` covers identifiers and has no notion of credentials,
  which is the gap this fills.
  History rather than the diff, unlike every other check here:
  a secret committed and then removed in a later commit is still exposed,
  since the orphaned commit stays fetchable through the GitHub API.
  That needs `fetch-depth: 0`,
  and a shallow clone is refused rather than reported clean on a partial scan.
  Matched values are never printed, in the log or in the run summary.
  Blocking by default (`fail: true`), where non-blocking prose checks only annotate.
  `paths-ignore`, `allowlist-file`, and `config` inputs suppress false
  positives;
  note that gitleaks path patterns are Go regexes, not globs.
  The official `gitleaks/gitleaks-action` is deliberately not used:
  it is proprietary and requires a paid licence for organization accounts.
