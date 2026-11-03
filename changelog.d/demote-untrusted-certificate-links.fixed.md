- `check-links` reports a link whose host serves a certificate chain lychee does not trust ("SSL certificate not trusted") as a warning naming the URL, not a blocking failure.
  That is a fault of the host's chain or the runner's trust store, not a dead link, and it failed every notes repo that links `web.stanford.edu` on 2026-11-03 (#1416).
  A 404, a DNS error and a timeout still fail.
