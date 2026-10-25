- **`check-links`** --
  puts lychee's install directory on the `PATH` itself before it calls `lychee-action`,
  because the action's own `GITHUB_PATH` entry did not reach its `lychee` step on a self-hosted runner
  (`lychee: command not found`, exit 127), which failed every link check there.
