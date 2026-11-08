- `preview` and `quarto-publish` skip the runner-side Quarto install when `cluster-render` is on and the runner has the cluster ssh key,
  since the cluster image supplies Quarto.
  The install runs `sudo`, which lab runners lack (gha#1642).
  Without the key, `condor-batch` renders on the runner, so the install still runs.
- `preview` and `quarto-publish` retry the Quarto setup once after 30 seconds,
  since one 504 on the release download failed the whole job (gha#1667).
