"""Generate a site-root 404 page that redirects legacy docs paths.

A multiversion docs site publishes each version under its own subdirectory, so
changing the subdirectory naming scheme breaks every link written against the
old one. The most common case: a site that published the default branch's docs
to `/<branch>/` (the `insightsengineering/r-pkgdown-multiversion` layout) and
now publishes them to `/dev/` (pkgdown's own development-mode layout), leaving
every `/main/...` link dead.

GitHub Pages serves no server-side redirects, but it does serve a site-root
`404.html` for any path it cannot resolve. Rewriting the request from there
covers deep links (`/main/reference/index.html`), which a per-directory
`index.html` meta-refresh cannot -- it only catches the directory root.

Writing the page into the same output directory as the root landing page also
means it survives deployment: the workflow's "Deploy root landing page" step
runs with `clean: true` and a `clean-exclude` list that does not name the old
version directories, so anything written outside that directory is removed on
the next default-branch push.

Redirection needs JavaScript. Without it the page renders as an ordinary
not-found notice linking to the docs root.
"""

import html
import json
import os
import sys
from urllib.parse import urlsplit

from _site_output import docs_base_url, site_output_dir


def _path_matches_source(path, source):
    """Return True if `path` (a target or target prefix) would match `source`."""
    target_has_wildcard = path.endswith("*")
    target_clean = path[:-1].rstrip("/") if target_has_wildcard else path.rstrip("/")

    if "*" in source:
        src_prefix = source[:-1]
        src_bare = src_prefix.rstrip("/")
        if target_clean == src_bare:
            return True
        if target_clean.startswith(src_prefix):
            return True
        if target_has_wildcard and src_prefix.startswith(target_clean + "/"):
            return True
        return False
    elif "/" in source:
        if not target_has_wildcard:
            return target_clean == source
        target_prefix = path[:-1]
        return source.startswith(target_prefix)
    else:
        target_first_seg = target_clean.split("/")[0]
        return target_first_seg == source


def parse_legacy_paths(raw):
    """Parse an `old=new` mapping from a comma- or newline-separated string.

    Returns a list of (old, new) pairs with surrounding slashes and whitespace
    stripped. Raises ValueError on any entry that cannot redirect correctly, so
    a typo fails the build instead of silently publishing a dead or looping
    redirect.
    """
    pairs = []
    seen = set()
    for chunk in raw.replace(",", "\n").splitlines():
        entry = chunk.strip()
        if not entry:
            continue
        if entry.count("=") != 1:
            raise ValueError(
                f"legacy path entry {entry!r} must have the form 'old=new' "
                "(for example 'main=dev')"
            )
        old, new = (part.strip().strip("/") for part in entry.split("="))
        if not old or not new:
            raise ValueError(
                f"legacy path entry {entry!r} has an empty source or target"
            )
        if old == new:
            raise ValueError(
                f"legacy path entry {entry!r} redirects {old!r} to itself, "
                "which would loop"
            )
        if old in seen:
            raise ValueError(f"legacy path {old!r} is mapped more than once")

        # Wildcard validation
        if old == "*" or old.strip("/") == "*":
            raise ValueError(f"legacy path entry {entry!r} uses a bare '*' source")
        if new == "*" or new.strip("/") == "*":
            raise ValueError(f"legacy path entry {entry!r} uses a bare '*' target")

        if "*" in old:
            if old.count("*") > 1 or not old.endswith("*"):
                raise ValueError(
                    f"legacy path entry {entry!r} has a '*' that is not at the end of the source"
                )
        if "*" in new:
            if "*" not in old:
                raise ValueError(
                    f"legacy path entry {entry!r} has a '*' in the target with none in the source"
                )
            if new.count("*") > 1 or not new.endswith("*"):
                raise ValueError(
                    f"legacy path entry {entry!r} has a '*' that is not at the end of the target"
                )

        seen.add(old)
        pairs.append((old, new))

    for old, new in pairs:
        for other_old, _ in pairs:
            if _path_matches_source(new, other_old):
                raise ValueError(
                    f"legacy path target {new!r} matches source {other_old!r}, which would loop"
                )

    return pairs


def classify_legacy_paths(pairs):
    """Classify (old, new) pairs into exact mappings, prefix patterns, and legacy moved."""
    exact = {}
    prefixes = []
    moved = {}
    for old, new in pairs:
        if "*" in old:
            # Prefix glob: e.g. reference/*=latest-tag/man/*
            prefix = old[:-1]
            prefixes.append((prefix, new))
        elif "/" in old:
            # Exact whole-path: e.g. reference/index.html=latest-tag/reference.html
            exact[old] = new
        else:
            # Single-segment rename: e.g. main=dev
            moved[old] = new
    # Longest prefix wins among prefixes
    prefixes.sort(key=lambda item: len(item[0]), reverse=True)
    return exact, prefixes, moved


def base_path_of(base_url):
    """Return the path component of the docs base URL, e.g. "/repo/".

    The redirect has to strip this prefix before matching a version directory,
    because a project site is served from `/<repo>/` rather than the domain
    root. A user or organization site has no such prefix and yields "/".
    """
    path = urlsplit(base_url).path
    if not path.startswith("/"):
        path = "/" + path
    if not path.endswith("/"):
        path = path + "/"
    return path


def js_literal(value):
    """Return `value` as a JSON literal safe to embed in a <script> block.

    JSON does not escape `/`, so a value containing `</script>` would close
    the block early. These values come from repository configuration rather
    than from a visitor, but escaping is a one-liner and removes the question.
    """
    return json.dumps(value).replace("</", "<\\/")


def render(base_path, pairs, docs_url):
    """Return the 404 page's HTML."""
    escaped_docs_url = html.escape(docs_url, quote=True)
    exact, prefixes, moved = classify_legacy_paths(pairs)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Page not found</title>
<script>
(function () {{
  var basePath = {js_literal(base_path)};
  var exact = {js_literal(exact)};
  var prefixes = {js_literal(prefixes)};
  var moved = {js_literal(moved)};
  var path = window.location.pathname;
  if (path.indexOf(basePath) !== 0) {{
    return;
  }}
  var rest = path.slice(basePath.length);
  var cleanRest = rest.length > 0 && rest.charAt(rest.length - 1) === "/" ? rest.slice(0, -1) : rest;
  if (Object.prototype.hasOwnProperty.call(exact, cleanRest)) {{
    window.location.replace(
      basePath + exact[cleanRest] + window.location.search + window.location.hash
    );
    return;
  }}
  for (var i = 0; i < prefixes.length; i++) {{
    var prefix = prefixes[i][0];
    var target = prefixes[i][1];
    if (rest.indexOf(prefix) === 0) {{
      var remainder = rest.slice(prefix.length);
      var dest = target.indexOf("*") !== -1 ? target.replace("*", remainder) : target;
      window.location.replace(
        basePath + dest + window.location.search + window.location.hash
      );
      return;
    }}
    if (rest === prefix.slice(0, -1)) {{
      var dest = target.indexOf("*") !== -1 ? target.replace("*", "") : target;
      window.location.replace(
        basePath + dest + window.location.search + window.location.hash
      );
      return;
    }}
  }}
  var slash = rest.indexOf("/");
  var head = slash === -1 ? rest : rest.slice(0, slash);
  if (!Object.prototype.hasOwnProperty.call(moved, head)) {{
    return;
  }}
  var tail = slash === -1 ? "" : rest.slice(slash + 1);
  window.location.replace(
    basePath + moved[head] + "/" + tail + window.location.search + window.location.hash
  );
}})();
</script>
</head>
<body>
<h1>Page not found</h1>
<p>This page does not exist, or it moved to a different documentation version.</p>
<p><a href="{escaped_docs_url}">Go to the documentation home page</a></p>
</body>
</html>
"""


def main():
    raw = os.environ.get("LEGACY_PATHS", "")
    try:
        pairs = parse_legacy_paths(raw)
    except ValueError as e:
        print(f"Invalid legacy-paths input: {e}", file=sys.stderr)
        sys.exit(1)

    if not pairs:
        print("No legacy paths configured; not generating 404.html.")
        return

    base_url = docs_base_url()
    output_dir = site_output_dir()

    page = render(base_path_of(base_url), pairs, base_url)
    (output_dir / "404.html").write_text(page, encoding="utf-8")

    for old, new in pairs:
        if "*" in old or "/" in old:
            print(f"Legacy redirect: /{old} -> /{new}")
        else:
            print(f"Legacy redirect: /{old}/... -> /{new}/...")


if __name__ == "__main__":
    main()
