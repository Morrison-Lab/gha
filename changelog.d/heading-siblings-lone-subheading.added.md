- `check-heading-siblings`:
  also flag a numbered heading that is the only numbered heading at its level under its parent heading,
  such as a lone 1.1 under 1 (Ezra, 2026-11-20).
  The usual fix is to add another sibling or promote a child, not to remove the singleton,
  and the failure message says so.
  Reported when a pull request adds or changes the lone heading or its parent heading.
  Headings inside fenced divs (div titles, tabs) do not count,
  and `.unnumbered` and `.unlisted` headings are not counted as siblings but still act as parents.
  Consumers on the reusable workflow get the new rule without opting in.
  Pass `lone: false` to turn it off.
