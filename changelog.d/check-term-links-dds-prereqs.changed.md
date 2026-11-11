- `check-term-links` now defaults `terms-from` for `Morrison-Lab/dds` to mds, pds, sds, and lds, as it does for mlg ([gha#1523](https://github.com/Morrison-Lab/gha/issues/1523)).
  Before, dds had no default, so a term only a prerequisite site defines, such as "rank" from mds, could stay unlinked on a dds page with no finding.
  The lds site is private, so its terms load only when the caller passes the `WORKFLOW_TOKEN` secret.
  Without it, the lds clone warns and the other three sites still load.
