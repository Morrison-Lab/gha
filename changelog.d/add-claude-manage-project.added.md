- **New `claude-manage-project.yml` reusable workflow** (#589).
  Triages a newly-opened issue: applies a priority label and adds it to the
  project board.
  The job is gated to `OWNER`/`MEMBER`/`COLLABORATOR` issue authors, because
  the issue body reaches a write-capable agent; the caller stub must mirror
  that gate.
  Projects v2 writes need a `PROJECTS_TOKEN`, since `GITHUB_TOKEN` cannot
  reach them.
