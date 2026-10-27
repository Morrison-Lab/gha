- **`check-caller-permissions` says where it read each callee, and warns when `CCP_GHA_DIR` overrides the pinned refs.**
  Each call's output line names the ref and source.
  A run against a local gha checkout, which can report grants the pinned callee does not request,
  now prints a warning instead of passing for a normal run
  ([`lds#1468`](https://github.com/Morrison-Lab/lds/issues/1468)).
