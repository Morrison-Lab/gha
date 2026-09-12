- `claude-code-review.yml`: strip inline code spans before machine payloads in
  `classify-review-verdict.sh` (#862).
  An unterminated `<!--` inside an inline code span no longer blanks following
  lines in `strip_machine_payloads`, ensuring superseding verdict headings in
  prose remain visible to the classifier.
