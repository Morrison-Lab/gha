- `check-quarto-links`: a new `site-urls` input checks the `#fragment` of absolute links into the listed published sites, such as `https://morrison-lab.github.io/pds/` (gha#1034).
  Each linked page is fetched once, and the fragment must be an `id` on it, so an anchor that a sibling site renamed or moved is caught.
  A page that cannot be fetched is reported as unchecked, not as dead.
  It is off by default.
  Measured on `Morrison-Lab/lds` on 2026-11-15 with the mcs, mds, pds, sds and psw sites listed: 59 pages fetched, 85 links to missing anchors, including the five `pds/random-variables.html#def-random` links of Morrison-Lab/lds#2509.
