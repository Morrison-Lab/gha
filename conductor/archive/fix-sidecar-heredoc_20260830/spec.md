# Specification: claude-code-review sidecar failure comment bug (#764)

## Overview
In the `claude-code-review` workflow, when the denied-tools sidecar executes, it attempts to write output to `$GITHUB_OUTPUT` using a heredoc. If the output lacks a trailing newline, the heredoc remains unterminated, causing the workflow step to error out. As a result, the workflow never reaches the job that actually posts the failure comment to the pull request.

## Functional Requirements
- The denied-tools sidecar step must successfully write its output to `$GITHUB_OUTPUT` without causing a heredoc termination error.
- The workflow must successfully proceed to the failure comment job when denied tools are detected.

## Proposed Solution
- Append an explicit trailing newline to the denied-tools output before or during the write to the `$GITHUB_OUTPUT` heredoc to ensure it is properly terminated.

## Acceptance Criteria
- [ ] A test or manual verification shows that triggering a denied-tools violation correctly terminates the `$GITHUB_OUTPUT` heredoc.
- [ ] The workflow successfully reaches and executes the failure comment job instead of erroring out at the sidecar step.

## Out of Scope
- Refactoring the entire output mechanism away from heredocs.
- Changes to other workflows or sidecars unrelated to this specific heredoc termination issue.
