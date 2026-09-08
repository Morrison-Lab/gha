- **`classify-review-verdict.sh` reads a `review-data` payload's own
  `verdict` field before falling back to the prose scan** (#845). A review
  body carrying a well-formed `<!-- review-data: {...} -->` block (a
  `schema_version` key and a `verdict` of `CLEAN` or `NOT_CLEAN`, with
  `CLEAN` additionally requiring `findings` to be absent or empty) is now
  classified from that field directly, ahead of `strip_machine_payloads`
  discarding the block. The payload is read only from lines that are
  neither fenced nor blockquoted -- reusing the same fence-tracking state
  machine `strip_machine_payloads` uses below it, so the two agree on what
  counts as fenced -- so a `<!-- review-data: ... -->` comment someone was
  merely quoting inside a `> ...` blockquote or a fenced code block is no
  longer trusted as the live verdict. The JSON body is located with
  `json.JSONDecoder().raw_decode` rather than a non-greedy `(.*?)\s*-->`
  regex, so a `-->` inside a JSON string value (e.g. a `"note"` field) no
  longer truncates the payload into invalid JSON and silently falls back to
  the prose. Previously the classifier depended entirely on prose
  vocabulary it recognized, so a triage-exemption verdict like "No action
  -- ... does not need code review" scored `unrecognized` even though the
  same comment's payload already said `"verdict": "CLEAN"` (measured on
  sparta#1547). Independently, `clean_kw` now also recognizes `no action`,
  but only when it is the verdict line itself (the first content line under
  the `### Verdict` heading) rather than anywhere in the section -- a later,
  unrelated sentence that happens to start with "No action" (e.g. "No
  action has been taken since the last round") no longer overrides an
  earlier, real rejection. The separate `does not need (code )?review`
  keyword was removed rather than anchored, since it has no fixed position
  in the triage template for an anchor to key on.

- **A second review round tightened four more edges of the same
  classifier** (#845). The `no action` anchor above required only that the
  verdict line START with those two words, which also matched ordinary
  prose describing unresolved work ("No action was taken on the flaky
  test, but there are still open issues to resolve here."); it now
  additionally requires that the rest of the line carry no still-open
  vocabulary (`still`, `remain*`, `open`, `unresolved`, `outstanding`,
  `but`, `however`, `not yet`, `pending`) and no rejection keyword, and
  optionally allows a trailing `needed`/`required`/`necessary`. A heading
  and its verdict written on the same line (`### Verdict: No action --
  trivial`, `**Verdict:** No action -- ...`) used to keep the `Verdict:`
  label attached to the front of `content_lines[0]`, which defeated the
  line-anchored `no action` check; the label is now stripped so only the
  verdict content itself becomes `content_lines[0]`. The fence-tracking
  regexes shared by the payload scan and `strip_machine_payloads` only
  recognized 0-3 spaces of indentation before a fence marker, so a tab- or
  4-space-indented ` ``` ` fence around a stale `review-data` payload was
  not tracked as fenced and the payload inside it was trusted; both
  regexes now also recognize a fence preceded by a tab or by any number of
  spaces, and a payload line indented by a tab or 4+ spaces with no fence
  at all (CommonMark's plain indented code block) is excluded from the
  payload scan directly. Finally, the `no action` anchor used to run
  unconditionally against `content_lines[0]`, so an emphasis-only first
  line (a bare `**`) hid a real verdict stated on a later line; the anchor
  now runs against the first content line that is non-empty after
  `strip_emphasis`.
