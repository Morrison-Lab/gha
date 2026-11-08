- `check-runner-disk.sh` removes a `.git` folder that is not a valid repository
  from the job's workspace before checkout runs,
  so a job cancelled mid-checkout no longer leaves
  "--local can only be used inside a git repository" as an error annotation
  on the next job (gha#1720).
  Its private-copy staging also retries once,
  so a fast-forward during the copy no longer makes the hook run in place.
