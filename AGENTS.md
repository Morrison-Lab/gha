# Universal AI Agent Instructions (AGENTS.md)

This file defines standardized, vendor-neutral instructions for AI coding agents operating within Morrison-Lab repositories (OpenAI Codex CLI, Gemini CLI / Antigravity, Claude Code, Cursor, Aider, etc.).

## Instruction layering

`AGENTS.md` is the compact cross-agent policy contract defining standardized instructions across Morrison-Lab repositories.
In `Morrison-Lab/gha`, `CLAUDE.md` serves as the primary repository operator manual (documenting composite action architectures, test recipes, review guards, and versioning rules).
Load and consult `CLAUDE.md` for repo-specific implementation details;
`AGENTS.md` provides the cross-agent baseline that must not contradict it (such as standing `mwc`).

## Generalize instructions to every AI agent by default

Unless the user explicitly scopes an instruction to one agent, project, or session, apply it to every available AI-agent configuration and shared automation surface.
Do not treat the currently speaking agent as an implicit scope restriction.

## No empty promises

A commitment about your own future behaviour --- "going forward, I will X", "from now on I won't Y", "I'll always Z", "I won't do that again", "that is owed by me" --- must ship an implemented accountability mechanism in the same turn, or not be made at all.
A written rule or memory entry is the minimum and is always available;
a hook or equivalent guard is the right form when the condition is decidable automatically;
a filed issue covers work someone has to schedule.

A promise costs nothing to produce and changes no file, so no review, check, or reader can tell it apart from having acted.
It is worse than saying nothing, because silence leaves the problem visibly open while a promise closes it on the record.
Promising the mechanism itself in the future tense ("I'll add a guard for this") is the same empty promise one level down.

**An owed *action* needs a mechanism that will fire, not only one that records.**
"I owe this PR the ARDI loop", "the UMS pass is owed by me", "I still owe that follow-up" each commit to one specific outstanding step, and a written record documents it without doing it.
So arm the next step --- a scheduled wakeup or timer carrying it, a cron or scheduled task when the check-in must outlive this session, a PR watcher when the debt is a PR --- and report what you armed and the clock time it fires.
A durable record still clears such a debt and is the right answer when it is somebody else's to schedule.
It is the wrong instinct when the debt is yours and has a next step.
The implication runs one way: a timer fires once and dies, so it cannot keep a standing rule.

When no mechanism is worth building, drop the promise and state the plain fact instead.
See [`shared/workflow/no-empty-promises.md`](https://github.com/Morrison-Lab/ai-config/blob/main/shared/workflow/no-empty-promises.md).

## Interpret instructions broadly and maximize safe progress

Unless the user narrows a request, take the broad reading that advances its obvious objective and complete every safe, authorized, relevant step.
Do not reduce an instruction to the smallest literal action when its context makes a larger in-scope outcome clear.

## Status requests do not make issues report-only

Treat a request for status as a request to inspect live state and finish every safe, in-scope, concrete action that inspection reveals.
A report is the recap after the work, not a substitute for it.
When an issue cannot be fixed directly, carry it forward with an actual next action.
Every issue noticed, however small or outside the current task's scope, must at minimum be filed in the owning GitHub, GitLab, or equivalent tracker.
File it before reporting it.

## Upgrade a repo to `Morrison-Lab/gha` when it would benefit

`Morrison-Lab/gha` holds the lab's reusable GitHub Actions workflows.
A consumer repo calls one with a stub (`uses: Morrison-Lab/gha/.github/workflows/<name>.yml@vN`) instead of carrying its own copy.
When a repo you are working in hand-maintains a workflow gha already provides, migrate it rather than noting it --- the upgrade is the deliverable.
Candidates are duplication, drift from a shared version, a named fix gha carries that the local copy lacks, or a `.github/workflows/` that already calls gha for some workflows and not others.
Not candidates are a workflow with genuinely repo-specific logic gha does not model, a repo a prior decision deliberately pinned off gha, and a repo we cannot merge a PR to.
Take the inventory from gha's README "Available reusable workflows" table and each capability's tag from its Versioning section, since `@v1` was frozen and the recommended tag varies per workflow.
File the migration as its own issue and PR rather than folding it into whatever brought you to the repo.
Full rule, including the migration hazards and the review-guard case: [`shared/workflow/upgrade-to-gha.md`](https://github.com/Morrison-Lab/ai-config/blob/main/shared/workflow/upgrade-to-gha.md).

## Manage quota, including the structural kind

Treat token cost as a property of a workflow's **shape**, not only of the choices made inside one session.
Route bounded mechanical work to a cheaper model, a subagent, or a separately-billed CLI rather than the conductor's own tier, and compact or hand off before context bloat forces it.

Those are per-session levers, and their saving expires with the session.
Ask separately what a procedure costs *by construction*: instructions loaded at launch that only some tasks read, a judgment made twice that wants a deterministic check, a serial loop whose base moves faster than one round, a brief that enumerates a set instead of deriving it.
The deliverable there is a change to the workflow --- fixed in stride when small, filed with its measurement when not --- never a quieter run of the same procedure.

Human steps count as workflow shape, so say so when one is costly --- and ship a mechanism in the same reply rather than only a suggestion.
A written rule is the floor.
A visible marker at the moment of the action, a guard, or a setting that removes the option are the stronger rungs.
The decision stays the human's.

Two boundaries.
Efficiency never outranks correctness, so no saving is bought with a skipped verification or a shortened review.
And restructure in its own issue or PR, not inside whatever task happened to notice it.
See [`shared/workflow/restructure-for-efficiency.md`](https://github.com/Morrison-Lab/ai-config/blob/main/shared/workflow/restructure-for-efficiency.md).

## Keep ai-config and repo checkouts fresh

In every session --- at session start, and again periodically during long sessions --- refresh local state:

1. **The ai-config checkout.**
   Check that the local `ai-config` clone is on `main` and run `git pull --ff-only`.

2. **The consumer copies / symlinks.**
   Ensure `bootstrap.sh` has run so local agent config directories (`~/.gemini/skills`, `~/.claude`, `~/.codex/skills`, `~/.cursor/rules`, and when needed `~/.cursor/skills`) contain up-to-date symlinks.

3. **Working repo checkouts.**
   Keep `main` updated (`git fetch origin`, `git pull --ff-only`).

## Verify changes before pushing

No compiled app gates this repo.
CI ([`.github/workflows/_selftest.yml`](.github/workflows/_selftest.yml)) runs the end-to-end composite checks and standalone test suites directly.
Consult `CLAUDE.md` ("Tests") for capability-specific test recipes.
Common local unit tests include:

```sh
python3 check-non-standard-chars/tests/test_check_non_standard_chars.py
node lint-markdown/tests/test_list_item_splices.mjs
node lint-markdown/tests/test_table_splits.mjs
python3 -m pytest check-phi/tests/ -q
python3 -m pytest check-new-line-breaks/tests/ -q
python3 -m pytest check-typos/tests/ -q
bash check-junk-files/tests/test-check-junk-files.sh
bash check-formatting/tests/test-check-formatting.sh
```

## Worktree isolation

- **Always use a worktree.**
  When starting write/edit tasks in a repository, isolate into a dedicated `git worktree` (e.g. via `session-lock` / `git worktree add`) so parallel sessions never step on or clobber each other's working directory or branch state.

## Check the remote immediately before every push

See [`shared/workflow/check-before-pushing.md`](https://github.com/Morrison-Lab/ai-config/blob/main/shared/workflow/check-before-pushing.md).

- **Read the remote branch fresh, every time.**
  Run `git ls-remote --heads origin <branch>` immediately before every `git push` --- read-only, so it cannot itself change what it reports.
  An earlier `git fetch` is a measurement of a moment that has passed.
  If the remote tip is not an ancestor of the ref you are **pushing**, another agent is driving the branch: fetch and reconcile, never overwrite.
  That ref is `HEAD` only when the refspec says so --- `git push origin feature-x` from `main` pushes local `feature-x`, and comparing against `HEAD` goes quiet in exactly the dangerous case.

- **The branch you own is the one to check hardest.**
  Ownership is what suppresses the check.
  The `@claude` agent pushes to your branch on PR activity, a second CLI session can claim the same PR, and a human can push at any time --- none of which appears in your conversation.

- **Never bare `git push --force`.**
  Use `git push --force-with-lease --force-if-includes`.
  The lease alone is defeatable: it compares against your remote-tracking ref, so any background fetch silently satisfies it over the commits it was protecting.
  `--force-if-includes` (git 2.30+) closes that.
  Pairing `--force` *with* the lease is not a middle ground: git documents `-f, --force` as one that "disables that check, the other safety checks in PUSH RULES below, and the checks in `--force-with-lease`".
  A `stale info` refusal is not a reason to force either --- it means the remote branch is gone, so a plain push is the fix ([`memories/git.md`](https://github.com/Morrison-Lab/ai-config/blob/main/memories/git.md)).
  `ALLOW_FORCE_PUSH=1` is an escape valve for a case the guard did not foresee.
  State the reason when you use it.

## Timestamp recaps in local time

When printing a status recap or summary, include a timestamp in the user's local time zone (Pacific Time, `America/Los_Angeles` --- get it from `TZ=America/Los_Angeles date "+%Y-%m-%d %H:%M %Z"`).
Each reading expires immediately: run the command fresh for every recap rather than extrapolating elapsed time from a prior reading.

## Temporal limitations on software and technology facts

Facts about software, platforms, libraries, APIs, harnesses, CLI tools, and runtime platforms are empirical observations of a specific version, release, or snapshot, not timeless definitions.
When recording facts about any software or technology across memories, documentation, PR descriptions, commit messages, or comments:

- Qualify them with explicit temporal bounds and provenance (date measured, version number, or execution environment).

- State the vintage explicitly so future readers and sessions know when the fact was verified and to re-verify against current state rather than treating it as permanent.

- See [`shared/writing/timestamp-volatile-claims.md`](https://github.com/Morrison-Lab/ai-config/blob/main/shared/writing/timestamp-volatile-claims.md).

## Every comment you post to a forge says an agent posted it

See [`disclose-agent-authorship`](https://github.com/Morrison-Lab/ai-config/blob/main/shared/workflow/disclose-agent-authorship.md).

An agent driving `gh`/`glab` under the account holder's credentials posts as **that person**: their login, their avatar, a `MEMBER` association, and `type: User`.
Nothing in the API distinguishes such a comment from one they typed, so a reader deciding how much weight to give a claim, a status note, or a review has no way to tell which they are reading.
The forge cannot say it; the body must.

End every comment an agent posts with this line, on its own, after a blank line:

```markdown
_Posted by Claude Code (AI agent) --- not written by a human._
```

Substitute your own agent's name where you are not Claude Code, and keep the rest of the line verbatim so one query finds every disclosed comment.
Check the substituted **name** against `REVIEW_BODY_MARKERS` as well as a replacement marker: `code review` is one of its entries, so an agent named for code review would reintroduce through its own name the false-clean the emoji ban exists to prevent.

The marker deliberately contains **no robot emoji**: [`scripts/check-pr-fully-clean.py`](https://github.com/Morrison-Lab/ai-config/blob/main/scripts/check-pr-fully-clean.py) matches that emoji as a review-body marker, so a disclosed claim comment would be admitted into the fully-clean verdict scan as a finding-free review.
Check any replacement marker against that script's `REVIEW_BODY_MARKERS` and `REVIEW_AGENT_MARKERS` before adopting it.

Scope: comment bodies, on every surface --- claims, releases, status notes, review replies, self-reviews, issue comments filed on the user's behalf.
Not commit messages, not titles, not issue bodies, not PR bodies, each of which has its own attribution convention.
Two exemptions.
A comment another machine parses as a command (`@dependabot rebase`), where the test is the audience rather than the length.
And a comment posted under a genuine bot token, where the forge already reports `type: Bot` and the marker adds nothing.

- **Do:** append the marker to every agent-posted comment, including ones whose prose already identifies the session.
- **Don't:** use the robot emoji in the marker, and don't read "the account holder knows an agent is running" as making the disclosure unnecessary --- the reader is whoever finds the thread later.

## File formatting & links

- Use GitHub-style markdown for all responses and documentation.
- When referencing files or code symbols in workspace paths, use relative markdown links (e.g. `[filename](relative/path/to/file)`) or inline code backticks (e.g. `` `path/to/file` ``).
- Preserve semantic line breaks (SemBr) and formatting conventions when editing markdown docs.

## Deliver completed implementation work

When asked to implement, edit, or write up a change on a feature branch, do not stop at an uncommitted worktree.
Complete the delivery cycle: create the applicable tracking issue when issue-first workflow applies, commit the scoped changes, run local adversarial self-review to a clean verdict, push the branch, open or update its Pull Request, request AI review after the final push, and drive CI and review findings to a clean result.
This does not grant merge authority.
The strict merge policy below still applies.

## Every self-review is an adversarial review by a separate subagent

Never push code to a remote branch blind, and never review your own diff in the context that wrote it.
Whenever reviewing your own work is called for --- before `git push`, as the fallback when the external reviewer is down, or the project-conventions pass --- dispatch it to a separate reviewer agent with an adversarial brief (the [`adversarial-reviewer`](https://github.com/Morrison-Lab/ai-config/blob/main/.claude/agents/adversarial-reviewer.md) subagent, or a separate CLI where no subagent tool exists), against `git diff origin/<default-branch>...HEAD`.
Address, rebut, or defer every finding, and obtain a clean verdict before pushing.

The authoring session cannot perform this itself.
It knows what the change was meant to say, so it reads the diff and recovers the intent --- confirmation rather than review --- and nothing in the output distinguishes that from a real pass.
Brief the reviewer with the diff and the standards, never with the rationale for the change.

In repositories with installed pre-push hooks (such as ai-config), pushing without a clean self-review is mechanistically blocked;
in this repo without local hooks, the rule is enforced procedurally.
Full rule, including why a same-vendor subagent buys independence of intent but not of blind spot: [`shared/workflow/adversarial-self-review.md`](https://github.com/Morrison-Lab/ai-config/blob/main/shared/workflow/adversarial-self-review.md).

## Put PRs in ready mode when they are ready for review

A Pull Request that is ready for review must be in ready mode, not left in draft.
Two paths satisfy this, and either is fine: open the PR ready for review when it already carries completed, verified work, or open it as a draft and mark it ready once it becomes ready for review.
What is not acceptable is leaving a review-ready PR in draft --- so do not rely on a harness or tool default that opens PRs as drafts and then forget to flip it: when the tool defaults to draft, either pass the flag that opens it ready or mark it ready once the work has landed.
Before marking a draft ready, verify the implementation actually reached the branch head and the repo's checks pass, and mind the ready-transition timing in [`pr-on-claim.md`](https://github.com/Morrison-Lab/ai-config/blob/main/shared/workflow/pr-on-claim.md): do not flip a draft to ready within seconds of the final push, which can race two review runs and leave the wrong one cancelled.
This overrides any agent-harness default that creates PRs as drafts unless the user opts in.

Draft status stays reserved for the cases that deliberately use draft as a signal or a gate, not only cases where work is unfinished: the empty up-front PR opened when claiming an issue (the [issue-first](https://github.com/Morrison-Lab/ai-config/blob/main/shared/workflow/issue-first.md) / [pr-on-claim](https://github.com/Morrison-Lab/ai-config/blob/main/shared/workflow/pr-on-claim.md) pattern), un-drafted once the implementation has landed on the branch head and the repo's checks pass;
and the deliberate draft-gating of a dependent PR, which is review-ready by construction and held in draft only to block the wrong merge order until its prerequisite merges.
Marking a PR ready grants no merge authority (see the strict merge policy below).

- **Do:** open a completed-work PR ready for review, or mark a draft ready once it is ready for review and its checks pass.

- **Do:** un-draft an up-front empty PR once its implementation has landed on the branch head and the checks pass.

- **Don't:** leave a PR that is ready for review in draft, except a deliberately draft-gated dependent PR held until its prerequisite merges.
- **Don't:** treat a tool's draft-by-default as the intended state once the work is ready for review.

## Antigravity Workspace Rules & Activation Scopes

- **Global rules**: Defined in `~/.gemini/GEMINI.md`.
- **Workspace rules**: Defined in `.agents/rules/` or root `AGENTS.md` (with backward compatibility for `.agent/rules/`).
- **Activation modes**:
  - *Always On*: Evaluated unconditionally in context (`alwaysApply: true` / root instruction files).
  - *Glob Scoped*: Evaluated when matching active workspace paths (`globs: [...]` or `applyTo: ...`).
  - *Model Decision*: Injected dynamically based on task context.
  - *Manual*: Triggered via `@mention` or explicit command.
- **Discovery manifests**: Configured via `.agents/skills.json` and `.agents/plugins.json`.

## Default to action without asking

The owner grants standing permission for non-destructive steps --- committing to a branch, pushing, opening or updating PRs against Morrison-Lab repositories, running non-destructive Git and API reads, and editing shared agent configurations.
Proceed with reasonable non-destructive steps and report them afterwards in the past tense.
Ask only for destructive, ambiguous, high-impact, or genuinely blocking choices.
This grants no merge authority: the strict merge policy below still applies.

(User directive, 2026-08-23: "always yes".)

## Strict Merge Control Policy

- **Standing `mwc` is active by default in `Morrison-Lab/gha`**: AI agent sessions working in this repository have standing permission to squash-merge pull requests once they reach **fully clean** (all CI checks green and zero outstanding review findings), unless explicitly instructed otherwise for a specific PR or session.

- **Never merge over open review findings or treat a reviewer skip notice as approval.**
  Under `mwc`, a PR must be fully clean across CI and review (see [`fully-clean.md`](https://github.com/Morrison-Lab/ai-config/blob/main/shared/workflow/fully-clean.md)).
  A clean automated AI review evaluating the current HEAD commit is strictly required for merging with `mwc`.
  A reviewer skip notice (e.g. for quota exhaustion or workflow edits) or a fallback self-review does NOT satisfy `mwc` or grant autonomous merge authority.
  All findings across the PR history must be Addressed, Rebutted, or Deferred before merge.

## Request review and drive every started PR to clean

Whenever starting or working on a Pull Request:

1. **Trigger AI review when done pushing**: In repositories where reviews do not auto-trigger, request an AI review (`@claude review` comment, or dispatch `claude-review.yml`) **after completing all code pushes** for the round, not when the PR is first opened and empty.
   In repos that automatically trigger review on PR events (`pull_request` synchronize, opened, ready_for_review), do NOT manually trigger a redundant review if an automated review is already running or queued.

2. **Drive to clean**: Run `ardi` / the review-and-iterate loop to ensure CI passes and all review findings are addressed until the PR reaches a clean verdict.
3. **Request human review only after AI approval or deadlock**: Per [`copilot-review-before-human.md`](https://github.com/Morrison-Lab/ai-config/blob/main/shared/vendored/copilot-review-before-human.md), request human review (configured repo reviewers per [`skills/request-pr-review/SKILL.md`](https://github.com/Morrison-Lab/ai-config/blob/main/skills/request-pr-review/SKILL.md)) **only after** the AI review produces a clean/approved verdict, or if an impasse/deadlock occurs.

- **Do:** Trigger AI review (or let the automated PR review run) after completing code pushes, and request human review only after the AI review is clean/approved (or upon an impasse).
- **Don't:** Manually trigger a redundant `@claude review` comment when an automated review is already running or triggered by the push/ready event.
- **Don't:** Request human review when the PR is first opened empty, before code pushes are complete, or before the AI review has passed / produced a clean verdict.
