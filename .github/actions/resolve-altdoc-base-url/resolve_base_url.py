"""Derive the GitHub Pages base URL used for altdoc multiversion docs links.

Shared by the generate-altdoc-version-dropdown and generate-altdoc-landing-page
composites so the derivation (and its fail-fast behavior when neither an
override nor enough GitHub Actions context is available) has one source of
truth, instead of two copies that can silently drift apart.
"""

import os
import sys


def resolve_base_url():
    """Return the base URL, always ending in exactly one trailing slash."""
    configured_url = os.environ.get("DOCS_BASE_URL", "").strip()
    if configured_url:
        return configured_url.rstrip("/") + "/"

    # GITHUB_REPOSITORY is one of GitHub Actions' default environment
    # variables and is always set in a real job -- this fallback only
    # matters for local/manual runs outside CI.
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if "/" in repository:
        owner, repo = repository.split("/", 1)
        if owner and repo:
            return f"https://{owner}.github.io/{repo}/"

    print(
        "Could not derive the docs base URL: set the base-url input, or run "
        "this action where GITHUB_REPOSITORY is set.",
        file=sys.stderr,
    )
    sys.exit(1)


if __name__ == "__main__":
    base_url = resolve_base_url()
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"base-url={base_url}\n")
    else:
        print(base_url)
