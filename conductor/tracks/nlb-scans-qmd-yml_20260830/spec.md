# Specification: check-new-line-breaks never scans .qmd or .yml (#750)

## Overview
The `check-new-line-breaks` tool currently ignores `.qmd` and `.yml` files because its default glob pattern (`NLB_GLOBS`) only targets `*.md`, and no caller overrides this default. This leaves Quarto documents and YAML workflows un-scanned for semantic line breaks. 

## Functional Requirements
- The default value of `NLB_GLOBS` within the script/action must be updated to include `*.md`, `*.qmd`, and `*.yml`.
- The `check-new-line-breaks` tool must successfully parse and validate semantic line breaks in `.qmd` and `.yml` files by default.
- Any existing `.qmd` or `.yml` files in the repository that currently violate the rules must be fixed so that the CI tests pass.

## Proposed Solution
- Modify the default `NLB_GLOBS` configuration in the `check-new-line-breaks` action/script to include the missing file extensions.
- Run the tool locally across the repository.
- Fix any newly discovered violations in `.yml` and `.qmd` files to ensure they conform to semantic line break standards.

## Acceptance Criteria
- [ ] A test or manual verification shows that the tool scans `.qmd` and `.yml` files by default.
- [ ] Running the semantic line break check on the entire repository passes successfully.
- [ ] All `.yml` and `.qmd` files in this repository conform to semantic line break rules.

## Out of Scope
- Modifying the core parsing logic or rules of the line break check itself.
