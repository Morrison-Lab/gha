"""Environment plumbing shared by this action's two generator scripts.

`generate_multiversion_landing_page.py` and `generate_legacy_redirects.py` run
back to back from the same `action.yml` and read the same two values, so the
`site-root` default and the base-URL lookup live here rather than once in each
script. The default in particular has to agree with `action.yml`'s own
`output-dir` default; keeping two hand-maintained copies is how those drift.
"""

import os
import pathlib

# Must match the `output-dir` input's default in action.yml. Only reached when
# a script is run directly (a test, a local invocation); the action always
# passes OUTPUT_DIR explicitly.
DEFAULT_OUTPUT_DIR = "site-root"


def site_output_dir():
    """Return the output directory, creating it if it does not exist."""
    output_dir = pathlib.Path(os.environ.get("OUTPUT_DIR", DEFAULT_OUTPUT_DIR))
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def docs_base_url():
    """Return the base URL resolved by the action's "Resolve base URL" step.

    Deliberately a KeyError rather than a default: the step that sets it runs
    unconditionally before both generators, so a missing value means the
    action is wired wrong and should fail loudly instead of writing a page
    with silently wrong links.
    """
    return os.environ["DOCS_BASE_URL"]
