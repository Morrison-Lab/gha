- `condor-batch` gains a `fallback-head` input: heads tried only after every `head`, never chosen by the spreading (gha#2091).
  `preview`'s default cluster heads now spread over csci-head (and the csci-lab pool with an image file), with cse-head as the last fallback,
  because cse-head's queue held jobs for a median of 16 minutes and a 90th percentile of 311 minutes, where the CSCI heads started them within seconds.
