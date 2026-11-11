- `claude.yml` now refuses a fork PR when the agent job runs on a self-hosted runner,
  and comments on the PR to say why,
  since that job holds a write token and checks out the PR head (gha#1217).
