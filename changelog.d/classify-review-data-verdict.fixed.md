- **`classify-review-verdict.sh` classifies from a review's `review-data` payload first, and recognises the triage-exemption verdict** ([#845](https://github.com/Morrison-Lab/gha/issues/845)).
  A body carrying a `<!-- review-data: {...} -->` block with a `schema_version` and a `verdict` of `CLEAN` or `NOT_CLEAN` is classified from that field,
  ahead of the prose scan,
  which stays the fallback for bodies without one.
  A `CLEAN` payload with a non-empty `findings` list is not trusted and falls through to the prose scan.
  The payload is read only from lines that are neither fenced, blockquoted, nor indented as code,
  through the same fence-tracking helper `strip_machine_payloads` uses,
  so a quoted stale payload no longer overrides the live verdict.
  The JSON is parsed with `json.JSONDecoder().raw_decode`,
  so a `-->` inside a JSON string cannot truncate it.
  Previously the classifier read prose only,
  so the triage-exemption verdict "No action -- automated, trivial PR that does not need code review" scored `unrecognized` while the same comment's payload said `CLEAN`
  (measured on [Lacaedemon/sparta#1547](https://github.com/Lacaedemon/sparta/pull/1547)).
  The prose scan now also accepts a verdict line that begins with `No action` (optionally `needed`, `required`, or `necessary`),
  but only on the first non-empty content line under the verdict heading,
  only when the rest of that line carries no still-open vocabulary or rejection keyword,
  and with a heading-and-verdict-on-one-line form (`### Verdict: No action -- trivial`) stripped to its content first.
  The looser `does not need (code )?review` phrase was deliberately not added.
  Fences preceded by a tab or any run of spaces are now tracked as fences.
  Blockquoted lines are now also blanked before the verdict-heading and prose scans,
  the same way they were already blanked before the payload scan,
  so a quoted `### Verdict` heading or a quoted `Ready for merge`/`Needs more work` keyword can no longer win the classification.
