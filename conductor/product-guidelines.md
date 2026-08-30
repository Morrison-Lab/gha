# Product Guidelines: Reusable GitHub Actions for Morrison-Lab (gha)

## Voice and Tone
- **Authoritative & Clear**: Documentation and logs should be precise, factual, and direct. Avoid jargon where simple language suffices.
- **Helpful & Actionable**: Error messages and checks (e.g., linter outputs, PHI/secrets scanning) must clearly state *why* they failed and *how* to fix the issue.
- **Professional**: Maintain a neutral, professional tone suitable for academic and research software engineering.

## UX Principles
- **Minimal Configuration**: Workflows should work out-of-the-box for standard R packages and Quarto sites with sensible defaults.
- **Fail Fast**: Security (secrets, PHI) and quality (linting, tests) checks must fail early in the CI/CD pipeline to prevent compromised or broken code from merging.
- **Visibility**: Status checks and bot comments should be concise and easily readable within GitHub pull request threads.
