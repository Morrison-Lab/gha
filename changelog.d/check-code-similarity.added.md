- **New capability: `check-code-similarity`** (#296).
  Flags code in a PR that is highly similar to a caller-supplied corpus of
  prior submissions, wrapping
  [JPlag](https://github.com/jplag/JPlag).
  Similarity is computed entirely on the runner --- nothing is uploaded, which
  is why JPlag was chosen over MOSS, whose comparison submits source to
  Stanford's servers.

- **The corpus is the caller's to assemble**, so the check needs no token, no
  cloning, and no policy on how many repositories is too many.
  A committed directory, a submodule, a second checkout, or a downloaded
  artifact all work.
  JPlag treats each *child directory* of a root as one submission, and a root
  holding loose files is refused rather than compared against nothing.

- **A finding warns rather than failing, by default.**
  Shared skeleton code, a common idiom, and a genuinely small assignment all
  raise similarity legitimately, so a high score is a prompt to look rather
  than a verdict.
  `base-code-path` excludes a provided framework; `fail: true` turns the
  signal into a gate once a threshold has been calibrated.

- **Everything that cannot run is an error.**
  A similarity check that fails to run prints no findings, which is exactly
  what a check that ran and found nothing prints.
  A missing corpus, an empty corpus, a corpus of loose files, a digest
  mismatch on the pinned jar, a JPlag crash, a missing or malformed results
  file, two roots sharing a directory name, and a comparison that produced no
  pair involving the submission under review all fail the step; a clean run
  reports how many pairs it examined.

- **JPlag's own diagnostics are kept out of the job log.**
  They quote source, so on a failed run they are written to the work directory
  --- under the same opt-in that governs the report --- and the log gets the
  exit code and a pointer instead.

- **Known limitation:** JPlag's R grammar does not parse R's native pipe
  `|>`, and the step surfaces a count of the resulting parse errors rather
  than swallowing them, because dropped tokens make the reported similarity a
  lower bound.
  Detection degraded rather than failed when measured: a copy with every
  identifier renamed still scored 1.0.
