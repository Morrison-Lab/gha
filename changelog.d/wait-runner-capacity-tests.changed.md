- **`wait-runner-capacity.sh`'s header describes the ticket-based worker limit, and tests cover the live worker count**
  ([#1553](https://github.com/Morrison-Lab/gha/issues/1553)).
  The tests now run the anchored `pgrep` pattern against stand-in workers and a decoy,
  check the running count in the hold message,
  and show a second held job starting after the first finishes.
