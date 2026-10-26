- **`check-ai-tells` no longer installs about 150 recommended apt packages while setting up R** (#1197).
  The `Set up R` step took 18 minutes on a slow Ubuntu mirror, so the job hit its 20-minute limit while the scan itself took seconds.
