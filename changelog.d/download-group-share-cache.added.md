- `check-secrets`, `check-typos`, and `lint-workflows`: on a runner that can see the group share, the gitleaks, typos, and actionlint archives are taken from `/cluster/research-groups/morrison/ci/release-cache` when a copy there matches its pinned checksum.
  A download that matches its pinned checksum is stored there for the next job, and any other runner downloads as before.
  The release host answered 504 to every retry on the cf463 runners between 08:52Z and 08:55Z on 2026-11-08, so retries alone could not keep these jobs green (gha#1667).
  Set `GHA_RELEASE_CACHE_DIR` to use another directory.
