`claude-review.yml`'s `/review` command now also accepts `claude[bot]`,
alongside the existing `cursor[bot]` allowlist entry and the
OWNER/MEMBER/COLLABORATOR associations.
This is the only review-request pathway a Claude Code remote/web session has:
its pushes carry `sender.type == 'Bot'`, which skips the reusable workflow's
automatic `pull_request` path, and a `workflow_dispatch` it issues itself
starts a run that `claude-code-action` short-circuits at zero cost, because
`allowed-bots` admits `github-actions[bot]` and not `claude[bot]`.
The `/review` dispatch runs under `GITHUB_TOKEN`, so it re-enters as
`github-actions[bot]` and clears both gates without widening either.
