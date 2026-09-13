- `claude-code-review.yml`: allow contradicting label-form verdict tails to
  supersede machine payloads in `classify-review-verdict.sh` (#863).
  A trailing label-form verdict tail (`Verdict:`, `**Verdict:**`) that
  genuinely contradicts an earlier payload's polarity now stands down the fast
  path so the prose scan decides, while confirming tails continue to classify
  from the payload without standing it down.
