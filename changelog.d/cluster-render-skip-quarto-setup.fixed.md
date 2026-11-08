`preview` and `quarto-publish` skip the runner-side Quarto install when `cluster-render` is on and the runner has the cluster ssh key,
since the cluster image supplies Quarto.
The install runs `sudo`, which lab runners lack (gha#1642).
Without the key, `condor-batch` renders on the runner, so the install still runs.
