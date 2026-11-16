- **Local Quarto renders on a self-hosted host now take one of a few per-host render slots** (gha#2062).
  `scripts/with-render-slot.sh` wraps the render step of `preview` and `quarto-publish`,
  and `condor-batch` takes a slot when it falls back to running its steps on the runner.
  The slot count is the host's memory divided by `RENDER_GB_PER_SLOT` (default 4 GB), or `RENDER_SLOTS`,
  and a render waits for a free slot for as long as its job's timeout allows.
  The job-started capacity hold gives up after 2 minutes so that short checks are not cancelled,
  so it let eleven jobs, most of them renders, onto cf463-02 at once on 2026-11-16.
  GitHub-hosted runners skip the slot.
