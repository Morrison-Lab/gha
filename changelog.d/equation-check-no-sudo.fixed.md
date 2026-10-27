- **`check-equation-renders`: install Chromium without `--with-deps` where sudo is unavailable.**
  A self-hosted runner without passwordless sudo failed the Playwright install step,
  so the equation check failed before it crawled anything.
  The action now passes `--with-deps` only for root or passwordless sudo,
  and the runner must then carry Chromium's system libraries.
