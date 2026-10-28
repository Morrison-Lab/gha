- **`runs-on` input on `check-note-sheet-rows.yml`**, defaulting to `ubuntu-latest` so existing callers are unaffected.
  The job hard-coded the hosted runner, so a private repository could not send it to a self-hosted one ([gha#1227](https://github.com/Morrison-Lab/gha/issues/1227)).
