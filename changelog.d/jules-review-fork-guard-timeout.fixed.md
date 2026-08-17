- **Add fork guard and job timeout to `jules-review.yml`** ([#372](https://github.com/Morrison-Lab/gha/issues/372)).
  Adds repository fork check `if: github.event.pull_request.head.repo.full_name == github.repository`
  to prevent hard failures from missing secrets on fork PRs, and adds `timeout-minutes: 40` to bound hung runs.
