- **`check-bibliography-dois` no longer fails a registered DOI whose
  publisher landing page returns 404** (gha#1017).
  doi.org redirects to the publisher's page, so a 404 there can mean the
  publisher moved the page rather than that the DOI does not exist.
  On a 404, the check now asks the Crossref API whether the DOI is
  registered.
  If Crossref returns 200, the entry passes with a warning that the landing
  page could not be verified.
  If Crossref does not know the DOI, or the lookup itself fails, the entry
  still fails as before.
  Other error statuses, such as 410, do not consult Crossref.
