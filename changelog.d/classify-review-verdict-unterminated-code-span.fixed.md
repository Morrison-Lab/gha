- `claude-code-review.yml`: strip inline code spans before machine payloads in
  `classify-review-verdict.sh` (#862).
  An unterminated `<!--` inside an inline code span no longer blanks following
  lines in `strip_machine_payloads`, preventing that marker shape from hiding
  subsequent verdict headings from the prose scan.
