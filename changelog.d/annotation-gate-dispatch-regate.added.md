- **A commit can be gated again by dispatching the annotation gate with its SHA** (#1610).
  `examples/annotation-gate-run.yml` gains a `workflow_dispatch` trigger with a `head-sha` input.
  Re-triggering the gate no longer needs a completed run of a path-filtered workflow on the commit, which a pull request touching only other files never has.
  `annotation-gate-run.yml`'s `run-id` input is now optional, because `all-runs` does not use it.
  Callers that copied the stub add the trigger and the `|| inputs.head-sha` fallback to use it.
