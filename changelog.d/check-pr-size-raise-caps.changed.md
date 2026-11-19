- `check-pr-size` defaults to 20 files and 600 lines, up from 10 and 300
  (Ezra, 2026-11-19: "we need to raise the pr size limit so you stop bothering me";
  [ai-config#5873](https://github.com/Morrison-Lab/ai-config/issues/5873)).
  A caller that passes `max-files` or `max-lines` keeps its own cap.
