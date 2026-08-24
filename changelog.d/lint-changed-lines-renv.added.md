- Add use-renv, 
env-cache-version, and pt-packages inputs to lint-changed-lines composite action and reusable workflow (gha#615).
- Supports restoring dependencies from 
env.lock via 
-lib/actions/setup-renv with custom cache versioning.
- Installs specified system packages via pt-get before restoring dependencies, and guarantees gh and lintr availability under renv environments.
