- **`student-qmd`** installs Quarto through the `install-quarto` release-cache action,
which falls back to the setup action, so a release-host outage does not stop the first attempt;
the second setup attempt after a failure is unchanged (gha#1678).
