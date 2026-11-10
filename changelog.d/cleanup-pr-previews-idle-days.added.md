- Add an `idle-days` input to `cleanup-pr-previews.yml` (default `0`, disabled).
  When greater than `0`, the preview of an open pull request whose last update is
  older than that many days is removed too, and the pull request's next push
  rebuilds it. Keeps a repository with many long-lived open PRs under the 1 GB
  GitHub Pages artifact cap
  ([gha#1814](https://github.com/Morrison-Lab/gha/issues/1814)).
