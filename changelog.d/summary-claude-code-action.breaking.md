`summary.yml` now runs `claude-code-action` with the `CLAUDE_CODE_OAUTH_TOKEN` secret, because the GitHub Models endpoint it called is retiring ([gha#617](https://github.com/Morrison-Lab/gha/issues/617), [gha#1133](https://github.com/Morrison-Lab/gha/issues/1133)).
The `endpoint` input and the `API_KEY` and `OPENAI_API_KEY` secrets are removed, so delete `with: endpoint:` from the caller.
Callers drop `models: read`, pass `secrets: inherit`, and move to `@v3`.
