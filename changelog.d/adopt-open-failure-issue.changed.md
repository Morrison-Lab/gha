- **`check-links.yml` and `website-publish.yml`:**
  Adopt `open-failure-issue` in `check-links.yml` so broken-link reports deduplicate against existing open issues,
  and add a `report-failure` job to `website-publish.yml` dogfooding the failure-reporting workflow (#327).
