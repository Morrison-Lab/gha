- **The runner job-started capacity hold** now waits at most 2 minutes by default, down from 4.
  The hold counts against the job's timeout,
  so a 4-minute hold left a 5-minute check 45 seconds for checkout and work and the job was cancelled (gha#1718).
