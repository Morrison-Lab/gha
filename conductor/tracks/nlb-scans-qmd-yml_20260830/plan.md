# Implementation Plan: check-new-line-breaks never scans .qmd or .yml (#750)

## Phase 1: Update Tool Defaults
- [x] Task: Locate and Update Default Globs (Red/Green Phase) [9cde105]
  - [x] Identify where `NLB_GLOBS` or equivalent default globs are defined in the `check-new-line-breaks` action or script.
  - [x] Update any applicable tool tests to ensure `.qmd` and `.yml` files are expected to be scanned.
  - [x] Modify the default configuration to include `**/*.md **/*.qmd **/*.yml` (or the correct syntax).
  - [x] Verify the tool's core tests still pass.

## Phase 2: Fix Repository Violations
- [x] Task: Discover Violations (932 violations found)
  - [x] Execute `check-new-line-breaks` across the repository to identify non-compliant `.yml` and `.qmd` files.
- [x] Task: Fix Violations (Skipped)
  - [x] Reformat violating files to conform strictly to semantic line breaks. (Removed from scope by user decision)
  - [x] Run the check again and ensure a completely clean pass across the repository. (Removed from scope)

## Phase 3: Phase Verification & Checkpoint
- [x] Task: Phase Verification & Checkpoint
