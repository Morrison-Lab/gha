- `check-pr-size` defaults to a 20-file cap and a 600-line cap, doubled from the old defaults
  (Ezra, 2026-11-19: "we need to raise the pr size limit so you stop bothering me";
  [ai-config#5873](https://github.com/Morrison-Lab/ai-config/issues/5873)).
  A caller that passes `max-files` or `max-lines` keeps its own cap.
