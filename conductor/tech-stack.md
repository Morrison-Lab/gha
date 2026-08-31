# Technology Stack: Reusable GitHub Actions for Morrison-Lab (gha)

## Languages

- **YAML**: Used for defining GitHub Actions workflows and composite actions.
- **Python**: Used for custom validation scripts (e.g., PHI checks, custom linters).
- **R**: Used for package-specific checks and integrations (`lintr`, `testthat`, `covr`).
- **Shell / Bash**: Used for orchestration and executing tools within GitHub Actions runners.

## Infrastructure & Automation

- **GitHub Actions**: The core CI/CD platform.
- **Quarto**: Used for scientific and technical publishing workflows.

## Quality & Security Tools

- **Code Quality**: `markdownlint-cli2`, `yamllint`, `lintr`, `actionlint`
- **Security**: `gitleaks` (secret scanning), `zizmor` (Actions security)
- **Content Validation**: `lychee` (link checking), `typos` (spellchecking)
