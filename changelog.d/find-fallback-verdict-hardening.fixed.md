- **`find-fallback-verdict` ignores a `Reviewed-Commit:` line or agent marker that is quoted rather than posted.**
  Text inside a code fence, a blockquote or an indented code block no longer counts, so quoting a review does not record one.
  The trust model is now written down and pinned by a test: the PR author's own marked comment counts, because the lab's agent sessions post under the account holder's login.
  The composite gains two test-only inputs, `comments-file` and `head-sha`, and `_selftest.yml` calls it through real `uses: ./` steps in both directions, which proves its script paths and input passthrough
  ([gha#1182](https://github.com/Morrison-Lab/gha/issues/1182)).
