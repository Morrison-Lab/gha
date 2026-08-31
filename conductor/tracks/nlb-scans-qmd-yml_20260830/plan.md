# Implementation Plan: check-new-line-breaks never scans .qmd or .yml (#750)

## Phase 1: Update Tool Defaults
- [ ] Task: Locate and Update Default Globs (Red/Green Phase)
  - [ ] Identify where `NLB_GLOBS` or equivalent default globs are defined in the `check-new-line-breaks` action or script.
  - [ ] Update any applicable tool tests to ensure `.qmd` and `.yml` files are expected to be scanned.
  - [ ] Modify the default configuration to include `**/*.md **/*.qmd **/*.yml` (or the correct syntax).
  - [ ] Verify the tool's core tests still pass.

## Phase 2: Fix Repository Violations
- [ ] Task: Discover Violations
  - [ ] Execute `check-new-line-breaks` across the repository to identify non-compliant `.yml` and `.qmd` files.
- [ ] Task: Fix Violations
  - [ ] Reformat violating files to conform strictly to semantic line breaks.
  - [ ] Run the check again and ensure a completely clean pass across the repository.

## Phase 3: Phase Verification & Checkpoint
- [ ] Task: Phase Verification & Checkpoint (Refer to workflow.md)
