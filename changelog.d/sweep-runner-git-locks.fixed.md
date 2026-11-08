The runner job-completed hook now removes stale `index.lock` files left in a checkout or its submodules.
It skips the sweep while a git process runs in the work folder, so a live lock is never removed.
A killed job no longer makes the next checkout on that runner fail (gha#1661).
