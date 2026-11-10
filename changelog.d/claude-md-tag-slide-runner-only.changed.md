- **`CLAUDE.md` no longer grants every agent session the `v3` tag slide**
  ([#1614](https://github.com/Morrison-Lab/gha/issues/1614)).
  Only the runner thread dispatches `slide-major-tag.yml`,
  and it slides without waiting for Ezra's typed "slide v3"
  ([#1834](https://github.com/Morrison-Lab/gha/issues/1834)).
