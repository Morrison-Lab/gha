- **`scripts/register-self-hosted-runner.sh`** --
  new runners now default `RUNNER_WORK_DIRECTORY` to `/tmp/gha-work/<runner name>`,
  because cf463-01's 28 GB `/var` filled up and jobs failed the disk check (gha#1564).
  Runners already configured keep their work folder.
