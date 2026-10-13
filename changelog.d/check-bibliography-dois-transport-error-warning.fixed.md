- **`check-bibliography-dois` downgrades a persistent resolver timeout or network error to a warning when Crossref knows the DOI.**
  A DOI whose publisher host timed out on every attempt (for example `projecteuclid.org`)
  failed the check even though the DOI was valid.
  After the retries, the action now asks Crossref about the DOI.
  A Crossref record turns the failure into a "not verified" warning, as a persistent 5xx already does,
  and a DOI Crossref cannot confirm still fails.
