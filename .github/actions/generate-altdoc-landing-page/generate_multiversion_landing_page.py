"""Generate the root multiversion landing-page redirect for GitHub Pages.

This mirrors the r-pkgdown-multiversion pattern: keep docs in versioned
subdirectories and use the root page as a redirect entrypoint.

Ported from d-morrison/rpt's `.github/scripts/generate_multiversion_landing_page.py`
into a reusable composite action (d-morrison/gha#284). Called by the
`altdoc-multiversion-docs` reusable workflow after the docs subdirectory
(dev / latest-tag / vX.Y.Z) for this build has been decided, and after this
action's own "Resolve base URL" step (the resolve-altdoc-base-url composite,
shared with generate-altdoc-version-dropdown) has already set DOCS_BASE_URL.
"""

import os
import pathlib
import sys


def main():
    target = os.environ["LANDING_TARGET"].strip("/")
    if not target:
        print("LANDING_TARGET must not be empty", file=sys.stderr)
        sys.exit(1)

    output_dir = pathlib.Path(os.environ.get("OUTPUT_DIR", "site-root"))
    output_dir.mkdir(parents=True, exist_ok=True)

    # Resolved by this action's own preceding "Resolve base URL" step.
    base_url = os.environ["DOCS_BASE_URL"]
    url = f"{base_url}{target}/"
    repo_name = os.environ.get("GITHUB_EVENT_REPOSITORY_NAME") or os.environ.get(
        "GITHUB_REPOSITORY", ""
    ).split("/")[-1]
    html = (
        "<!DOCTYPE html>\n"
        '<meta charset="utf-8">\n'
        f"<title>{repo_name}</title>\n"
        f'<meta http-equiv="refresh" content="0; URL={url}">\n'
        f'<link rel="canonical" href="{url}">\n'
    )

    (output_dir / "index.html").write_text(html, encoding="utf-8")
    (output_dir / ".nojekyll").write_text("", encoding="utf-8")

    print(f"Generated root redirect to: {url}")


if __name__ == "__main__":
    main()
