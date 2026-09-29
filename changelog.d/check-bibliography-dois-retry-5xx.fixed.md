- **`check-bibliography-dois` retries transient 5xx/429 resolver responses and downgrades persistent 5xx to warnings** (#982).
  A single 5xx or rate limit from `doi.org` or an upstream publisher previously failed
  the PR check on its first attempt with no retries.
  The action now retries 5xx server errors and 429 rate limits up to three times with exponential backoff,
  downgrades persistent 5xx server errors to non-failing warnings when the resolver remains unavailable,
  and preserves immediate failures for 404 client errors and missing DOI fields.
