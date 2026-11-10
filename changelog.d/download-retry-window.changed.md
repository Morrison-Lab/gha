- `cached_download` retries a failing release download 20 times, 15 s apart (about 5 minutes),
  up from 8 times, 10 s apart,
  so the lychee, gitleaks, typos, Quarto, and TinyTeX installs outlast a longer release-host 504 burst.
  `GHA_DOWNLOAD_RETRIES` and `GHA_DOWNLOAD_RETRY_DELAY` override the two numbers
  ([gha#1740](https://github.com/Morrison-Lab/gha/issues/1740)).
