- **The runner cleanup hook's low-space warning says what it measured** --
  when `scripts/prune-runner-workdir.sh` has removed every other checkout and the disk is still under the limit,
  its warning now names the folder it measured, the filesystem and mount point `df` answered for,
  the free space, and the sizes of the work folder and the current job's checkout.
  Runner `private-cf463-01-5` warned "still has under 10 GB free", which fails the Annotation gate,
  while `/var` showed 17 GB free afterwards, and the old warning gave no way to tell a wrong mount from a transient peak.
