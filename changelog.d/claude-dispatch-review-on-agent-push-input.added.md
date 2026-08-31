- `claude.yml`: add `dispatch-review-on-agent-push` boolean input (default `true`) (#778).
  Allows consumers to disable automatic review dispatches after agent commits
  and require explicit `@claude review` requests.
