- **New `check-dependency-graph.yml` reusable workflow**
  ([#1129](https://github.com/Morrison-Lab/gha/issues/1129)).
  It runs the self-test of a repository's vendored `build_dependency_graph.py`.
  It then builds the graph and fails on a cycle.
  Notes repos that vendor the script from `build-dependency-graph` call it in place of a per-repo workflow.
