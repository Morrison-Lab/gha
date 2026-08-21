- `claude.yml`: a new `dispatch-on-assignee` input makes assigning an issue a
  sufficient trigger on its own, with no `@claude` mention required anywhere in
  the issue ([#298](https://github.com/Morrison-Lab/gha/issues/298)).

  Assignment is already a deliberate act by someone with repository access, so
  it needs no content signal the way `opened` does.
  The input takes a JSON array of logins and is empty by default, so nothing
  changes for a consumer that does not opt in.

  It gates on the assignee rather than on whoever did the assigning, because the
  `issues.assigned` payload carries no `author_association` for the sender --
  checking the assigner's write access would need an API call from inside the
  job, after the gate has already let the run start.

  Purely additive.
  An assigned issue whose body or title mentions `@claude` already dispatched
  before this and still does.

  Two halves are required, the same way `trusted-bot-logins` needs both.
  Setting the input alone does nothing, because every clause in the stock
  caller gate requires a mention, so the reusable workflow is never invoked.
  `examples/claude.yml` carries the literal caller clause to add.
