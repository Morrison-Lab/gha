- **The OpenCode review workflow (`opencode-code-review.yml@v2`) now retries transient Zen stream drops** ([#600](https://github.com/Morrison-Lab/gha/issues/600)).
  Retries a failed run when the attempt died with the transient Zen stream-drop signature
  (`finish_reason: network_error`),
  governed by a new `opencode-attempts` input (default 3, range 1-5).
  Auth, quota, and other failures never match the retry signature and stay single-shot.
