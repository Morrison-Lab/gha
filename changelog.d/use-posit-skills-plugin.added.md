- **`claude-code-review.yml` and `claude.yml` install the Posit developer skills plugin by default**
  (#877).
  Both workflows gain a `use-posit-skills` boolean input (on by default)
  that registers `https://github.com/posit-dev/skills.git` as a plugin marketplace
  and installs the `posit-dev@posit-dev-skills` plugin.
  In review runs,
  this provides the `critical-code-reviewer` rubric
  (severity tiers, edge cases, and constructive scrutiny),
  composing alongside the built-in `code-review@claude-code-plugins`
  and `ai-config@Morrison-Lab`.
  In agent runs,
  it equips Claude with Posit's general-purpose developer skills
  (`describe-design`, `implement`, `review-testing`, and `working-on`).
  Callers can opt out by passing `use-posit-skills: false`.
