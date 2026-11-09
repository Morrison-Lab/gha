- **`check-runner-disk.sh` and `prune-runner-workdir.sh` name where a symlinked work folder points**
  ([gha#1585](https://github.com/Morrison-Lab/gha/issues/1585)).
  A runner whose work folder is a link, such as `/var/tmp/gha-work/<runner>` pointing into `/tmp`,
  used to report the link's path beside the filesystem of its target,
  so a reader could not tell which disk was measured.
  The low-disk messages now say `<path> (a link to <target>)`.
