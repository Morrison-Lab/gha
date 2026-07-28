- **The `@claude` agent and reviewer now install the `ai-config` plugin by
  default** (#319).
  Both workflows install `ai-config@d-morrison` from
  [`Morrison-Lab/ai-config`](https://github.com/Morrison-Lab/ai-config) unless the
  caller passes `use-ai-config: false`, so a repo picks up the lab's shared
  skills, commands, and review conventions without listing them itself.
  No caller-side change is needed to get this; opting out is one input.
