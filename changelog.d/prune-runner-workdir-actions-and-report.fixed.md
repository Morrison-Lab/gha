- **The runner cleanup hook frees `_actions` and names the largest folders when the disk stays low** --
  when `scripts/prune-runner-workdir.sh` has removed every other checkout and the disk is still under the limit,
  it now also removes the runner's `_actions` folder, which the runner re-downloads,
  and its warning lists the largest folders in the work folder.
  Runner `private-cf463-01-5` kept warning "still has under 10 GB free", which fails the Annotation gate,
  with no hint of what held the space.
