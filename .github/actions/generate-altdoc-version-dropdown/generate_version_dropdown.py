"""Generate a Quarto navbar version dropdown for multiversion altdoc sites.

Reads the current dev version from DESCRIPTION and all release tags from git,
then rewrites the "Versions" menu block in an altdoc `quarto_website.yml` so
that:
  - The current stable release is labeled "vX.Y.Z (stable)" -> /latest-tag/ URL
  - The development build is labeled "<version> (dev)"      -> /dev/ URL
  - A separator followed by each older tag links to /vX.Y.Z/ (previous versions)
  - The menu's own label names the version this build renders, instead of a
    static "Versions" that leaves a reader unable to tell which version's
    docs they landed on (d-morrison/gha#307)

It also gives the navbar title a pkgdown-style version badge; see
`navbar_version.py`, which holds the version-labeling and navbar-rewriting
helpers this script orchestrates.

Ported from d-morrison/rpt's `.github/scripts/generate_version_dropdown.py`
into a reusable composite action (d-morrison/gha#284) so altdoc-based R
packages don't each carry their own copy. Called by the
`altdoc-multiversion-docs` reusable workflow before `render_docs()`, after
this action's own "Resolve base URL" step (the resolve-altdoc-base-url
composite) has already set DOCS_BASE_URL.
"""

import subprocess
import re
import sys
import os
from pathlib import Path

from navbar_version import (
    DEV_SUFFIX,
    GENERATED_MARKER,
    STABLE_SUFFIX,
    find_versions_entry,
    format_dropdown_title,
    parse_bool,
    resolve_current_version,
    set_navbar_title,
    version_badge_html,
    yaml_quote,
)

REPO_DIR = Path(os.environ.get("DOCS_SOURCE_DIR", ".")).resolve()
DEFAULT_BRANCH = os.environ.get("DEFAULT_BRANCH", "main").strip() or "main"
QUARTO_CONFIG_PATH = (
    os.environ.get("QUARTO_CONFIG_PATH", "altdoc/quarto_website.yml").strip()
    or "altdoc/quarto_website.yml"
)
CURRENT_VERSION = os.environ.get("CURRENT_VERSION", "").strip()
DROPDOWN_TITLE_TEMPLATE = (
    os.environ.get("DROPDOWN_TITLE_TEMPLATE", "").strip() or "{version}"
)

try:
    VERSION_IN_NAVBAR_TITLE = parse_bool(
        "version-in-navbar-title",
        os.environ.get("VERSION_IN_NAVBAR_TITLE", "").strip() or "true",
    )
except ValueError as e:
    print(e, file=sys.stderr)
    sys.exit(1)

# --- Helpers ---


def _parse_version(content):
    """Return the Version field from DESCRIPTION file content, or None."""
    for line in content.splitlines():
        m = re.match(r"^Version:\s+(.+)", line)
        if m:
            return m.group(1).strip()
    return None


def _run_git(*args):
    """Run a git command in REPO_DIR and return the CompletedProcess result.

    Runs with cwd=REPO_DIR rather than the process's own working directory --
    DOCS_SOURCE_DIR can point at a linked worktree checked out for a stable-tag
    release build (same repo, so this wouldn't matter) or, in a test fixture,
    an entirely separate repo (where it does matter: without an explicit cwd,
    `git tag`/`git show` would silently resolve against whatever repo the
    calling step happens to be in instead).

    Calls sys.exit(1) with a descriptive message if the git executable
    cannot be launched (e.g. git not installed or permission denied).
    """
    try:
        return subprocess.run(
            ["git", *args], capture_output=True, text=True, cwd=REPO_DIR
        )
    except OSError as e:
        print(f"Failed to execute git command: {e}", file=sys.stderr)
        sys.exit(1)


# Resolved by this action's own preceding "Resolve base URL" step
# (resolve-altdoc-base-url), shared with generate-altdoc-landing-page so the
# override/derivation/fail-fast logic has one source of truth.
BASE_URL = os.environ["DOCS_BASE_URL"]

# --- Gather version information ---

# The version of the checkout actually being rendered: the release version on
# a release build (which renders a tag worktree), the branch's development
# version otherwise.  This is what tells us which docs version this build IS,
# when the caller doesn't say so via `current-version`.
local_version = None
local_error = "no Version field in DESCRIPTION"
try:
    with open(REPO_DIR / "DESCRIPTION") as f:
        local_version = _parse_version(f.read())
except OSError as e:
    local_error = f"could not open DESCRIPTION: {e}"

# Get the development version from DESCRIPTION.
# On release builds the checked-out DESCRIPTION contains the release version
# (e.g. "1.0.0"), not the dev version.  Read origin/<default-branch>:DESCRIPTION
# instead so the /dev/ link is always labeled with the actual development
# version.  Fall back to the local file if the git command fails (e.g. no
# remote, or running against a fixture with no origin/<default-branch>).
dev_version = None

result = _run_git("show", f"origin/{DEFAULT_BRANCH}:DESCRIPTION")
if result.returncode == 0:
    dev_version = _parse_version(result.stdout)

if dev_version is None:
    dev_version = local_version

if dev_version is None:
    print(f"Could not determine the package version ({local_error})", file=sys.stderr)
    sys.exit(1)

if local_version is None:
    local_version = dev_version

# Get release tags (vX.Y.Z only; tags with a dev component like v1.0.0.9000
# are excluded because they are not final releases)
release_tags = []
release_query_succeeded = False

gh_token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
github_repository = os.environ.get("GITHUB_REPOSITORY")
if gh_token and github_repository:
    try:
        result = subprocess.run(
            [
                "gh",
                "api",
                f"repos/{github_repository}/releases",
                "--paginate",
                "--jq",
                '.[] | select(.draft == false and .prerelease == false) | .tag_name',
            ],
            capture_output=True,
            text=True,
            env={**os.environ, "GH_TOKEN": gh_token},
        )
    except OSError as e:
        # `gh` missing/unrunnable is the same "can't use the API" case as a
        # failed API call below -- fall through to the `git tag` fallback
        # rather than aborting, since that fallback exists precisely to cover
        # environments where the API path doesn't work.
        print(f"Could not execute gh command ({e}); falling back to git tag", file=sys.stderr)
        result = None
    if result is not None and result.returncode == 0:
        release_query_succeeded = True
        all_tags = result.stdout.strip().split("\n") if result.stdout.strip() else []
        release_tags = [t for t in all_tags if re.match(r"^v\d+\.\d+\.\d+$", t)]

if not release_query_succeeded and not release_tags:
    result = _run_git("tag", "--sort=-version:refname")
    if result.returncode != 0:
        print(f"git tag command failed:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    all_tags = result.stdout.strip().split("\n") if result.stdout.strip() else []
    release_tags = [t for t in all_tags if re.match(r"^v\d+\.\d+\.\d+$", t)]


def _semver_key(tag):
    return tuple(int(part) for part in tag.lstrip("v").split("."))


release_tags = sorted(set(release_tags), key=_semver_key, reverse=True)
latest_tag = release_tags[0] if release_tags else None
prev_tags = release_tags[1:] if len(release_tags) > 1 else []

# --- Locate and replace the Versions block in quarto_website.yml ---

quarto_config_file = REPO_DIR / QUARTO_CONFIG_PATH
try:
    with open(quarto_config_file) as f:
        lines = f.readlines()
except OSError as e:
    print(f"Could not open {quarto_config_file}: {e}", file=sys.stderr)
    sys.exit(1)

# Find the navbar's Versions menu: the literal "- text: Versions" entry, or
# the marker this action leaves behind once it has relabeled that entry.
entry = find_versions_entry(lines)
if entry is None:
    print(
        f'Could not find "- text: Versions" entry in {quarto_config_file} '
        "navbar configuration",
        file=sys.stderr,
    )
    sys.exit(1)
block_start, start_idx, indent = entry
base = " " * indent        # same indent level as the Versions menu entry
mi = " " * (indent + 2)    # menu: key
ii = " " * (indent + 4)    # individual menu items

# Find the end of the Versions block (first non-blank line at same or lower indent)
end_idx = start_idx + 1
while end_idx < len(lines):
    line = lines[end_idx]
    if line.strip() == "":
        end_idx += 1
        continue
    if len(line) - len(line.lstrip()) <= indent:
        break
    end_idx += 1

# --- Build the new Versions block ---

# Which of the entries below this build is rendering, so the menu's own
# label can name it instead of a static "Versions".
try:
    current = resolve_current_version(
        local_version, release_tags, latest_tag, CURRENT_VERSION
    )
    dropdown_title = format_dropdown_title(DROPDOWN_TITLE_TEMPLATE, current.label)
except ValueError as e:
    print(e, file=sys.stderr)
    sys.exit(1)

new_block = [
    f"{base}{GENERATED_MARKER}\n",
    f"{base}- text: {yaml_quote(dropdown_title)}\n",
    f"{mi}menu:\n",
]

if latest_tag:
    new_block += [
        f"{ii}- text: {yaml_quote(latest_tag + STABLE_SUFFIX)}\n",
        f"{ii}  href: {BASE_URL}latest-tag/\n",
    ]

if dev_version:
    new_block += [
        f"{ii}- text: {yaml_quote(dev_version + DEV_SUFFIX)}\n",
        f"{ii}  href: {BASE_URL}dev/\n",
    ]

if prev_tags:
    # "---" renders as a visual divider in the Quarto navbar dropdown
    new_block.append(f'{ii}- text: "---"\n')
    for tag in prev_tags:
        new_block += [
            f'{ii}- text: "{tag}"\n',
            f"{ii}  href: {BASE_URL}{tag}/\n",
        ]

new_lines = lines[:block_start] + new_block + lines[end_idx:]

# --- Show the current version on the navbar title, pkgdown-style ---

navbar_title = None
if VERSION_IN_NAVBAR_TITLE:
    # new_block leads with the marker, so its `- text:` entry -- the line
    # `set_navbar_title` walks up from to find the navbar -- sits one below.
    new_lines, navbar_title = set_navbar_title(
        new_lines, block_start + 1, version_badge_html(current)
    )
    if navbar_title is None:
        print(
            f"::warning::{quarto_config_file} has no navbar or site title to "
            "attach the version badge to; the Versions menu label still names "
            f"the current version ({current.label}).",
        )

# Write the updated file
try:
    with open(quarto_config_file, "w") as f:
        f.writelines(new_lines)
except OSError as e:
    print(f"Could not write to {quarto_config_file}: {e}", file=sys.stderr)
    sys.exit(1)

print(f"Current version: {current.label}")
if navbar_title is not None:
    print(f"Navbar title: {navbar_title}")
print("Updated Versions dropdown:")
print("".join(new_block))

github_output = os.environ.get("GITHUB_OUTPUT")
if github_output:
    with open(github_output, "a") as f:
        f.write(f"latest-tag={latest_tag or ''}\n")
        f.write(f"dev-version={dev_version or ''}\n")
        f.write(f"current-version={current.label}\n")
