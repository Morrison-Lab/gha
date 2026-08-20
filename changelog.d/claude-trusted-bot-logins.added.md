- **`claude.yml` gains a `trusted-bot-logins` input** (JSON array, default
  `[]`). GitHub App bots whose `author_association` is `NONE` (e.g.
  `cursor[bot]` posting `@claude review` from a Cloud Agent) can opt into the
  same trigger path as OWNER/MEMBER/COLLABORATOR humans. Callers must mirror
  the allowlist in their job-level `if:` -- otherwise the reusable workflow is
  never invoked. This repo's dogfood `claude-bot.yml` and `claude-review.yml`
  admit `cursor[bot]` on the caller side; pass `trusted-bot-logins:
  '["cursor[bot]"]'` under `with:` only after `@v2` has slid past this merge
  (an unknown `workflow_call` input fails every `@claude` run at the call
  gate).
