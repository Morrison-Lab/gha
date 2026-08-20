- Document in `CLAUDE.md` that green `require-review` is not fully clean:
  agent sessions must read the latest review comment body at the current head
  SHA before declaring a PR clean or invoking standing `mwc` merge (gha#527).
