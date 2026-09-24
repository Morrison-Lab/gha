- **`dispatch-on-comment` posts notice via REST API and supplies default branch fallback** (#931).
  `gh issue comment` posts via GraphQL `addComment`, requiring `pull_requests: write`
  on PRs and failing under the job's `issues: write` scope. Switched notice
  posting to `POST /repos/{owner}/{repo}/issues/{issue_number}/comments` with
  `Content-Type: application/json` and `jq -Rs '{body: .}'`.
  Additionally, explicitly pass `--ref "$DEFAULT_BRANCH"` on fallback paths
  (such as fork PRs and workflow-editing PRs) across `claude-review.yml`,
  example workflows, `dispatch-review.sh`, and `dispatch-review` action,
  avoiding `gh workflow run`'s unauthenticated GraphQL `defaultBranchRef`
  query on private repositories.
