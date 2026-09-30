#!/usr/bin/env python3
"""Update vendored Quarto extensions in-place to upstream semver tags.

Scans `_extensions/**/_extension.yml` to find vendored Quarto extensions,
resolves their upstream GitHub repositories from an input mapping (with
built-in defaults for common extensions), queries upstream tags,
verifies that local vendored copies have not been edited locally, and updates
them in-place while strictly preserving directory layout (flat vs nested).

Modelled on bump-submodule.yml and open-sync-pr.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_EXTENSION_REPOS: Dict[str, str] = {
    "code-language-labels": "d-morrison/code-language-labels",
    "div-anchors": "d-morrison/div-anchors",
    "equation-anchors": "d-morrison/equation-anchors",
    "slidebreak": "Morrison-Lab/slidebreak",
    "revealjs-html-links": "d-morrison/revealjs-html-links",
}

SEMVER_PATTERN = re.compile(
    r"^v?(?P<major>\d+)(?:\.(?P<minor>\d+))?(?:\.(?P<patch>\d+))?"
    r"(?:-(?P<prerelease>[0-9A-Za-z.-]+))?"
    r"(?:\+(?P<build>[0-9A-Za-z.-]+))?$"
)


def parse_semver(v_str: str) -> Optional[Tuple[int, int, int, int, str]]:
    """Parse a version string into a comparable tuple.

    Returns:
        (major, minor, patch, is_stable, prerelease_str) or None.
        is_stable is 1 if prerelease is None, else 0, so stable versions
        sort higher than prereleases of the same numeric version.
    """
    if not v_str:
        return None
    m = SEMVER_PATTERN.match(v_str.strip())
    if not m:
        return None
    major = int(m.group("major"))
    minor = int(m.group("minor") or 0)
    patch = int(m.group("patch") or 0)
    prerelease = m.group("prerelease")
    is_stable = 1 if prerelease is None else 0
    return (major, minor, patch, is_stable, prerelease or "")


def parse_repo_map(raw_map: str) -> Dict[str, str]:
    """Parse user-provided extension repository mapping.

    Supports JSON format (`{"ext": "owner/repo"}`) or YAML/multiline
    key-value format (`ext: owner/repo`).
    """
    if not raw_map or not raw_map.strip():
        return {}

    raw_clean = raw_map.strip()
    if raw_clean.startswith("{") and raw_clean.endswith("}"):
        try:
            parsed = json.loads(raw_clean)
            if isinstance(parsed, dict):
                return {str(k).strip(): str(v).strip() for k, v in parsed.items()}
        except Exception:
            pass

    # Line-by-line key-value parsing
    result: Dict[str, str] = {}
    for line in raw_clean.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            k = k.strip().strip("'\"")
            v = v.strip().strip("'\"")
            if k and v:
                result[k] = v
        elif "=" in line:
            k, v = line.split("=", 1)
            k = k.strip().strip("'\"")
            v = v.strip().strip("'\"")
            if k and v:
                result[k] = v
    return result


def read_manifest_fields(manifest_path: pathlib.Path) -> Dict[str, str]:
    """Extract metadata fields from _extension.yml without requiring PyYAML."""
    content = manifest_path.read_text(encoding="utf-8", errors="replace")
    fields: Dict[str, str] = {}

    for key in ("title", "author", "version", "id"):
        # Match `key: value` or `key: "value"`
        pattern = rf"^{key}:\s*(?:['\"](?P<quoted>[^'\"]+)['\"]|(?P<raw>[^#\r\n]+))"
        m = re.search(pattern, content, re.MULTILINE)
        if m:
            val = (m.group("quoted") or m.group("raw") or "").strip()
            if val:
                fields[key] = val
    return fields


def find_vendored_extensions(extensions_root: pathlib.Path) -> List[Dict[str, Any]]:
    """Locate all vendored extensions under extensions_root."""
    extensions: List[Dict[str, Any]] = []
    if not extensions_root.is_dir():
        return extensions

    for manifest_path in extensions_root.glob("**/_extension.y*ml"):
        if not manifest_path.is_file():
            continue

        ext_dir = manifest_path.parent
        rel_path = ext_dir.relative_to(extensions_root)
        fields = read_manifest_fields(manifest_path)

        extensions.append(
            {
                "dir": ext_dir,
                "rel_path": rel_path.as_posix(),
                "name": ext_dir.name,
                "manifest_path": manifest_path,
                "fields": fields,
                "version": fields.get("version", "0.0.0"),
            }
        )
    return extensions


def resolve_upstream_repo(
    ext_info: Dict[str, Any], repo_map: Dict[str, str]
) -> Optional[str]:
    """Resolve GitHub owner/repo for an extension."""
    rel_path = ext_info["rel_path"]
    name = ext_info["name"]
    ext_id = ext_info["fields"].get("id", "")
    title = ext_info["fields"].get("title", "")

    # Look up by relative path, name, id, title
    for key in (rel_path, name, ext_id, title):
        if key and key in repo_map:
            return repo_map[key]
    return None


def fetch_github_api(
    endpoint: str, token: Optional[str] = None
) -> Any:
    """Fetch GitHub REST API endpoint using gh CLI or urllib."""
    clean_endpoint = endpoint.lstrip("/")

    # Prefer gh CLI when present
    if shutil.which("gh"):
        cmd = ["gh", "api", clean_endpoint]
        try:
            res = subprocess.run(
                cmd, capture_output=True, text=True, check=True
            )
            return json.loads(res.stdout)
        except subprocess.CalledProcessError as e:
            err = (e.stderr or "").strip()
            print(
                f"Notice: 'gh api {clean_endpoint}' failed ({err}); "
                "falling back to urllib.",
                file=sys.stderr,
            )
        except Exception as e:
            print(
                f"Notice: 'gh api {clean_endpoint}' encountered error ({e}); "
                "falling back to urllib.",
                file=sys.stderr,
            )

    # Fallback to urllib.request
    url = f"https://api.github.com/{clean_endpoint}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Morrison-Lab-gha-update-quarto-extensions",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    elif os.environ.get("GH_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GH_TOKEN']}"
    elif os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def download_github_tarball(
    repo: str, ref: str, dest_tarball: pathlib.Path, token: Optional[str] = None
) -> None:
    """Download repository tarball for a given tag/ref."""
    if shutil.which("gh"):
        cmd = ["gh", "api", f"repos/{repo}/tarball/{ref}"]
        try:
            with open(dest_tarball, "wb") as f:
                subprocess.run(
                    cmd, stdout=f, check=True, stderr=subprocess.PIPE
                )
            return
        except subprocess.CalledProcessError as e:
            err = (
                e.stderr.decode("utf-8", errors="replace") if e.stderr else ""
            ).strip()
            print(
                f"Notice: 'gh api repos/{repo}/tarball/{ref}' failed ({err}); "
                "falling back to urllib.",
                file=sys.stderr,
            )
        except Exception as e:
            print(
                f"Notice: 'gh api repos/{repo}/tarball/{ref}' encountered "
                f"error ({e}); falling back to urllib.",
                file=sys.stderr,
            )

    url = f"https://api.github.com/repos/{repo}/tarball/{ref}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Morrison-Lab-gha-update-quarto-extensions",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    elif os.environ.get("GH_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GH_TOKEN']}"
    elif os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        with open(dest_tarball, "wb") as f:
            shutil.copyfileobj(resp, f)


def extract_tarball_extension_dir(
    tarball_path: pathlib.Path,
    extract_temp_dir: pathlib.Path,
    ext_name: str,
) -> Optional[pathlib.Path]:
    """Extract tarball and locate the extension directory within it."""
    with tarfile.open(tarball_path) as tf:
        if hasattr(tarfile, "data_filter"):
            tf.extractall(extract_temp_dir, filter="data")
        else:
            print(
                "::warning::Python tarfile PEP 706 data filter unavailable; "
                "extracting without filter.",
                file=sys.stderr,
            )
            tf.extractall(extract_temp_dir)

    # GitHub tarballs unpack into {owner}-{repo}-{sha}/
    extracted_roots = [
        d for d in extract_temp_dir.iterdir() if d.is_dir()
    ]
    if not extracted_roots:
        return None
    root = extracted_roots[0]

    # Search for _extension.yml in extracted archive
    candidates = list(root.glob("**/_extension.y*ml"))
    if not candidates:
        return None

    # Priority 1: matches _extensions/{ext_name}/_extension.yml
    for c in candidates:
        if c.parent.name == ext_name:
            return c.parent

    # Priority 2: candidate under _extensions/
    for c in candidates:
        if "_extensions" in c.parts:
            return c.parent

    # Priority 3: first candidate found
    return candidates[0].parent


def normalize_file_content(path: pathlib.Path) -> bytes:
    """Read file content with line endings normalized to LF."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    except Exception:
        return path.read_bytes()


def directories_match(dir_a: pathlib.Path, dir_b: pathlib.Path) -> bool:
    """Compare two directory trees ignoring hidden files and CRLF/LF."""
    def get_rel_files(d: pathlib.Path) -> Dict[str, pathlib.Path]:
        files: Dict[str, pathlib.Path] = {}
        for p in d.rglob("*"):
            if not p.is_file():
                continue
            if any(part.startswith(".") for part in p.relative_to(d).parts):
                continue
            rel = p.relative_to(d).as_posix()
            files[rel] = p
        return files

    files_a = get_rel_files(dir_a)
    files_b = get_rel_files(dir_b)

    if set(files_a.keys()) != set(files_b.keys()):
        return False

    for rel, path_a in files_a.items():
        path_b = files_b[rel]
        if normalize_file_content(path_a) != normalize_file_content(path_b):
            return False
    return True


def check_for_local_edits(
    local_dir: pathlib.Path,
    repo: str,
    current_version: str,
    tags: List[Dict[str, Any]],
    token: Optional[str] = None,
) -> bool:
    """Check if the local vendored copy matches an upstream release tag.

    Returns True if local files match at least one published upstream tag,
    False if they differ from all tested tags (indicating local modifications).
    """
    # Find matching tag(s) for the current version
    current_semver = parse_semver(current_version)
    tags_to_check: List[str] = []

    for t in tags:
        t_name = t.get("name", "")
        t_semver = parse_semver(t_name)
        if current_semver and t_semver and current_semver[:3] == t_semver[:3]:
            tags_to_check.insert(0, t_name)
        else:
            tags_to_check.append(t_name)

    # Check tags (prioritizing the tag matching current_version)
    with tempfile.TemporaryDirectory() as temp_dir_str:
        temp_dir = pathlib.Path(temp_dir_str)
        # Limit tag checks to avoid excessive downloads
        for tag_name in tags_to_check[:5]:
            tb_path = temp_dir / f"check-{tag_name}.tar.gz"
            extract_dir = temp_dir / f"extract-{tag_name}"
            extract_dir.mkdir(parents=True, exist_ok=True)
            try:
                download_github_tarball(repo, tag_name, tb_path, token=token)
                upstream_dir = extract_tarball_extension_dir(
                    tb_path, extract_dir, local_dir.name
                )
                if upstream_dir and directories_match(local_dir, upstream_dir):
                    return True
            except Exception:
                continue

    return False


def copy_extension_files(
    src_dir: pathlib.Path, dest_dir: pathlib.Path
) -> None:
    """Copy files from src_dir to dest_dir in-place, removing deleted files."""
    # Collect existing files/dirs in dest_dir to clean
    for item in dest_dir.iterdir():
        if item.name.startswith(".git"):
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()

    # Copy files from src_dir
    for item in src_dir.iterdir():
        if item.name.startswith(".git"):
            continue
        target = dest_dir / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


def update_extensions(
    extensions_dir: pathlib.Path,
    repo_map: Dict[str, str],
    dry_run: bool = False,
    allow_local_edits: bool = False,
    token: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Scan and update vendored Quarto extensions in-place.

    Returns a list of updated extension dicts.
    """
    vendored = find_vendored_extensions(extensions_dir)
    if not vendored:
        print(f"::notice::No vendored Quarto extensions found under '{extensions_dir}'.")
        return []

    updated_records: List[Dict[str, Any]] = []

    for ext in vendored:
        ext_name = ext["name"]
        local_dir = ext["dir"]
        rel_path = ext["rel_path"]
        current_version_str = ext["version"]
        current_semver = parse_semver(current_version_str)

        repo = resolve_upstream_repo(ext, repo_map)
        if not repo:
            print(
                f"::notice::Skipping vendored extension '{ext_name}' at '{rel_path}': "
                f"no upstream repository mapped in 'extension-repos'."
            )
            continue

        print(f"Checking '{ext_name}' ({rel_path}) against upstream {repo}...")

        try:
            tags_data = fetch_github_api(f"repos/{repo}/tags", token=token)
        except Exception as e:
            print(f"::warning::Failed to fetch tags for {repo}: {e}")
            continue

        if not tags_data or not isinstance(tags_data, list):
            print(f"::notice::No tags found for {repo}; skipping.")
            continue

        # Parse tags into valid semver candidates
        semver_tags: List[Tuple[Tuple[int, int, int, int, str], str]] = []
        for t in tags_data:
            t_name = t.get("name", "")
            t_sem = parse_semver(t_name)
            if t_sem:
                semver_tags.append((t_sem, t_name))

        if not semver_tags:
            print(f"::notice::No semver tags found for {repo}; skipping.")
            continue

        # Sort tags descending
        semver_tags.sort(key=lambda item: item[0], reverse=True)
        newest_semver, newest_tag_name = semver_tags[0]
        newest_version_str = newest_tag_name.lstrip("vV")

        if current_semver and newest_semver <= current_semver:
            print(
                f"::notice::Extension '{ext_name}' is already up to date "
                f"({current_version_str} >= {newest_version_str})."
            )
            continue

        print(
            f"Update available for '{ext_name}': {current_version_str} -> {newest_version_str} (tag {newest_tag_name})"
        )

        # Requirement 4: Fail loudly if vendored copy was modified locally
        if not allow_local_edits:
            clean_match = check_for_local_edits(
                local_dir, repo, current_version_str, tags_data, token=token
            )
            if not clean_match:
                msg = (
                    f"Vendored Quarto extension '{ext_name}' in '{rel_path}' differs "
                    f"from all published upstream release tags of {repo}. "
                    "It appears to have uncommitted or unversioned local edits. "
                    "Aborting to avoid clobbering local modifications."
                )
                print(f"::error title=update-quarto-extensions::{msg}", file=sys.stderr)
                raise RuntimeError(msg)

        # Requirement 3: Replace files in-place preserving layout
        if dry_run:
            print(
                f"[dry-run] Would update '{ext_name}' ({rel_path}) "
                f"from {current_version_str} to {newest_version_str}."
            )
            updated_records.append(
                {
                    "name": ext_name,
                    "path": rel_path,
                    "old_version": current_version_str,
                    "new_version": newest_version_str,
                    "repo": repo,
                    "tag": newest_tag_name,
                }
            )
            continue

        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = pathlib.Path(temp_dir_str)
            tarball_path = temp_dir / f"{ext_name}-{newest_tag_name}.tar.gz"
            extract_dir = temp_dir / "extract"
            extract_dir.mkdir(parents=True, exist_ok=True)

            download_github_tarball(repo, newest_tag_name, tarball_path, token=token)
            upstream_ext_dir = extract_tarball_extension_dir(
                tarball_path, extract_dir, ext_name
            )

            if not upstream_ext_dir:
                print(
                    f"::error::Could not find extension directory inside upstream archive for {repo}@{newest_tag_name}."
                )
                continue

            copy_extension_files(upstream_ext_dir, local_dir)

        print(
            f"Successfully updated '{ext_name}' in '{rel_path}' to {newest_version_str}."
        )
        updated_records.append(
            {
                "name": ext_name,
                "path": rel_path,
                "old_version": current_version_str,
                "new_version": newest_version_str,
                "repo": repo,
                "tag": newest_tag_name,
            }
        )

    return updated_records


def format_pr_title_and_body(
    updates: List[Dict[str, Any]]
) -> Tuple[str, str]:
    """Generate PR title and markdown body for the automation PR."""
    if not updates:
        return "", ""

    if len(updates) == 1:
        u = updates[0]
        title = f"chore: update Quarto extension {u['name']} to {u['new_version']}"
    else:
        title = "chore: update Quarto extensions"

    body_lines = [
        "Automated update of vendored Quarto extension(s):",
        "",
    ]
    for u in updates:
        body_lines.append(
            f"- **`{u['name']}`** in `{u['path']}`: `{u['old_version']}` -> `{u['new_version']}` "
            f"([upstream release](https://github.com/{u['repo']}/releases/tag/{u['tag']}))"
        )
    body_lines.extend(
        [
            "",
            "Generated by the `update-quarto-extensions` reusable workflow in "
            "[`Morrison-Lab/gha`](https://github.com/Morrison-Lab/gha).",
        ]
    )

    return title, "\n".join(body_lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Update vendored Quarto extensions in-place."
    )
    parser.add_argument(
        "--extensions-dir",
        default="_extensions",
        help="Path to the directory containing vendored extensions (default: _extensions).",
    )
    parser.add_argument(
        "--repo-map",
        default="",
        help="Custom mapping of extension names to owner/repo (JSON or key: value lines).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Detect and log updates without modifying files.",
    )
    parser.add_argument(
        "--allow-local-edits",
        action="store_true",
        help="Allow updating vendored copies that differ from upstream release tags.",
    )
    parser.add_argument(
        "--set-output",
        default="",
        help="Path to GITHUB_OUTPUT file.",
    )
    parser.add_argument(
        "--summary-file",
        default="",
        help="Path to GITHUB_STEP_SUMMARY file.",
    )
    parser.add_argument(
        "--token",
        default="",
        help="GitHub API token.",
    )

    args = parser.parse_args()

    extensions_path = pathlib.Path(args.extensions_dir)
    user_map = parse_repo_map(args.repo_map)
    combined_repo_map = {**DEFAULT_EXTENSION_REPOS, **user_map}

    try:
        updates = update_extensions(
            extensions_dir=extensions_path,
            repo_map=combined_repo_map,
            dry_run=args.dry_run,
            allow_local_edits=args.allow_local_edits,
            token=args.token or None,
        )
    except RuntimeError as err:
        sys.exit(1)

    pr_title, pr_body = format_pr_title_and_body(updates)
    is_updated = "true" if updates else "false"
    ext_list = ", ".join(u["name"] for u in updates)

    if args.set_output:
        out_path = pathlib.Path(args.set_output)
        with open(out_path, "a", encoding="utf-8") as f:
            f.write(f"updated={is_updated}\n")
            f.write(f"updated-extensions={ext_list}\n")
            if pr_title:
                f.write(f"pr-title={pr_title}\n")
            if pr_body:
                # GitHub Actions multiline output syntax
                f.write("pr-body<<EOF\n")
                f.write(pr_body)
                f.write("\nEOF\n")

    if args.summary_file and updates:
        sum_path = pathlib.Path(args.summary_file)
        with open(sum_path, "a", encoding="utf-8") as f:
            f.write("### Quarto Extensions Update\n\n")
            f.write(pr_body)
            f.write("\n")


if __name__ == "__main__":
    main()
