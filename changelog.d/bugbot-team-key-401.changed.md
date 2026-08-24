- **`cursor-code-review.yml` rejects a Team-plan `CURSOR_API_KEY`** (#601).
  The queue step fails with `HTTP 401 Invalid Team API Key` when the secret
  is a Team key rather than an Enterprise `admin:*` key.
  Team and individual installs should keep using dashboard Bugbot;
  that error is not missing `secrets:` wiring.
