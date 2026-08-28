- `opencode-code-review.yml`: the gha#600 transient-retry signature is now
  matched against the CLI's stderr only (#706).
  Scanning the model-generated review stdout too meant a review that merely
  quoted the signature could make an unrelated failure retryable,
  contradicting the documented only-the-transient-class guarantee;
  gha#600's observed failures all carry the signature on stderr.
