- **`check-caller-permissions` reference page now says to run the check at the pinned refs.**
  Running the script with `CCP_GHA_DIR` set to gha `main` reports grants that a caller's pinned
  callee does not request, which led to speculative grants and a wrong review finding
  ([`lds#1468`](https://github.com/Morrison-Lab/lds/issues/1468)).
