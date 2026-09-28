#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
"""
Report tracked image files that no tracked source file references.

A figure that stops being used -- its page rewritten, its chapter moved to an
outtake, a regenerated copy committed under a new name -- stays in the
repository forever, because nothing about a render notices a file it was
never asked to read. This is a source-tree check: nothing is rendered.

Design notes:

- **Population.** Tracked files (``git ls-files``) under ``OI_PATHS`` whose
  extension is in ``OI_EXTENSIONS``, minus ``OI_PATHS_IGNORE``. Only tracked
  files, so render output and untracked scratch images are never reported.
- **What counts as a use.** An image is used when its file name appears in
  any tracked file whose extension is in ``OI_SOURCE_EXTENSIONS`` (``.qmd``,
  ``.md``, ``.yml``, ``.scss``, ``.lua``, ``.html``, ... by default). Matching
  on the file name rather than on a resolved path is deliberate: a source
  refers to an image through a relative path, a root-relative path, a YAML
  key, a Lua string or a CSS ``url()``, and resolving every one of those
  would be a render. The cost is stated rather than hidden: two images that
  share a file name in different directories are both "used" when either
  is, and an image named only by a computed string (``paste0("fig", i)``)
  reads as unused and needs ``paths-ignore``.
- **Warn-only by default** (``OI_FAIL`` defaults to false): an unused file
  wastes space but breaks nothing, and a source-tree scan cannot see every
  way a file may be used.
- **Optionally diff-scoped.** With ``OI_BASE_REF`` set, only images the
  branch ADDED since its merge base with that ref are reported, so a first
  run on a repository with years of accumulated figures does not bury the
  one a PR just added. If the merge base cannot be computed (a shallow
  clone, an unknown ref) the check is skipped with a warning rather than
  widened to the whole tree, which is ``check-new-line-breaks``' rule.
- **Search space is reported**, so a run that examined nothing reads
  differently from a clean pass.

Configuration (environment variables, set by the composite action):
  OI_PATHS              Space-separated git pathspecs to look for images in
                        (default: '.').
  OI_EXTENSIONS         Comma/space-separated image extensions (default:
                        '.png, .jpg, .jpeg, .gif, .svg, .webp, .avif').
  OI_SOURCE_EXTENSIONS  Comma/space-separated extensions of files searched
                        for references (default: see DEFAULT_SOURCE_EXTENSIONS).
  OI_PATHS_IGNORE       Comma/newline-separated globs (``*``, ``?``, ``**``)
                        of images to skip.
  OI_BASE_REF           Empty => whole tree; otherwise only images added
                        since the merge base with this ref.
  OI_FAIL               'true' => exit 1 when an unused image is found.
"""

import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Iterable, List, NamedTuple, Optional, Set
from urllib.parse import unquote

DEFAULT_EXTENSIONS = ".png, .jpg, .jpeg, .gif, .svg, .webp, .avif"
DEFAULT_SOURCE_EXTENSIONS = (
    ".qmd, .md, .Rmd, .ipynb, .yml, .yaml, .scss, .css, .lua, .html, .tex, .bib"
)


# Characters that cannot be part of a file name as a source writes it (they
# delimit a Markdown link, an HTML attribute, a YAML value, a CSS url(), a
# fragment or a query string). Splitting on them, rather than searching for
# names with a lazy pattern, keeps the scan linear on long lines such as an
# inlined data URI.
_DELIMITERS_RE = re.compile(r"[\s\"'()<>\[\]{}|,;=`*!#?]+")


class Result(NamedTuple):
    examined: int
    sources: int
    orphans: List[str]


def _run_git(args: List[str]) -> Optional[str]:
    try:
        return subprocess.run(
            ["git", *args], capture_output=True, check=True,
            encoding="utf-8", errors="replace",
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _glob_to_regex(pat: str) -> "re.Pattern[str]":
    """Translate a path glob to an anchored regex; supports ``**``, ``*``, ``?``."""
    i, n, out = 0, len(pat), []
    while i < n:
        c = pat[i]
        if c == "*":
            if pat[i:i + 2] == "**":
                i += 2
                if pat[i:i + 1] == "/":
                    out.append("(?:.*/)?")
                    i += 1
                else:
                    out.append(".*")
            else:
                out.append("[^/]*")
                i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def compile_ignores(patterns: Iterable[str]) -> List["re.Pattern[str]"]:
    compiled = []
    for pat in patterns:
        compiled.append(_glob_to_regex(pat))
        if "*" not in pat and "?" not in pat:
            compiled.append(_glob_to_regex(pat.rstrip("/") + "/**"))
    return compiled


def parse_extensions(value: str) -> Set[str]:
    return {
        (tok if tok.startswith(".") else "." + tok).lower()
        for tok in re.split(r"[,\s]+", value or "") if tok.strip()
    }


def referenced_names(texts: Iterable[str], extensions: Set[str]) -> Set[str]:
    """Every file name with an image extension that appears in ``texts``.

    Names are collected both as written and URL-decoded (``my%20fig.png``),
    and lower-cased, since the file systems these sites are built on
    differ in case sensitivity and a case-only mismatch is not an orphan.
    """
    names: Set[str] = set()
    for text in texts:
        for tok in _DELIMITERS_RE.split(text):
            tok = tok.rstrip(".:")
            if not tok:
                continue
            for form in (tok, unquote(tok)):
                name = PurePosixPath(form.replace("\\", "/")).name
                if PurePosixPath(name).suffix.lower() in extensions:
                    names.add(name.lower())
    return names


def find_orphans(
    root: Path,
    images: List[str],
    sources: List[str],
    extensions: Set[str],
) -> List[str]:
    texts = []
    for rel in sources:
        try:
            texts.append((root / rel).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    names = referenced_names(texts, extensions)
    blob = None
    orphans = []
    for img in images:
        base = PurePosixPath(img).name
        if base.lower() in names:
            continue
        # A name with a space (or another character the tokenizer stops at)
        # is only reachable by a plain substring search, e.g. `<my fig.png>`.
        if _DELIMITERS_RE.search(base):
            if blob is None:
                blob = "\n".join(texts).lower()
            if base.lower() in blob:
                continue
        orphans.append(img)
    return orphans


def added_files(base_ref: str) -> Optional[Set[str]]:
    """Files added between the merge base with ``base_ref`` and HEAD."""
    mb = _run_git(["merge-base", base_ref, "HEAD"])
    if not mb or not mb.strip():
        return None
    out = _run_git(["diff", "--name-only", "-z", "--diff-filter=A", "--no-renames",
                    mb.strip(), "HEAD"])
    if out is None:
        return None
    return {f for f in out.split("\0") if f}


def tracked(pathspecs: List[str]) -> Optional[List[str]]:
    out = _run_git(["ls-files", "-z", "--", *pathspecs])
    if out is None:
        return None
    return sorted(f for f in out.split("\0") if f)


def run(
    paths: List[str],
    extensions: Set[str],
    source_extensions: Set[str],
    ignores: List["re.Pattern[str]"],
    only: Optional[Set[str]] = None,
    root: Path = Path("."),
) -> Optional[Result]:
    candidates = tracked(paths)
    everything = tracked(["."])
    if candidates is None or everything is None:
        return None
    images = [
        f for f in candidates
        if PurePosixPath(f).suffix.lower() in extensions
        and not any(r.match(f) for r in ignores)
        and (only is None or f in only)
    ]
    sources = [f for f in everything if PurePosixPath(f).suffix.lower() in source_extensions]
    return Result(len(images), len(sources), find_orphans(root, images, sources, extensions))


def main() -> int:
    paths = (os.environ.get("OI_PATHS") or ".").split()
    exts = parse_extensions(os.environ.get("OI_EXTENSIONS") or DEFAULT_EXTENSIONS)
    src_exts = parse_extensions(
        os.environ.get("OI_SOURCE_EXTENSIONS") or DEFAULT_SOURCE_EXTENSIONS
    )
    ignores = compile_ignores(
        t.strip() for t in re.split(r"[,\n]", os.environ.get("OI_PATHS_IGNORE", "")) if t.strip()
    )
    fail = os.environ.get("OI_FAIL", "false").strip().lower() == "true"
    base_ref = os.environ.get("OI_BASE_REF", "").strip()
    if not exts:
        print("::error::check-orphaned-images: `extensions` is empty, so nothing would be examined.")
        return 1

    only = None
    scope = "whole tree"
    if base_ref:
        only = added_files(base_ref)
        if only is None:
            print(
                f"::warning::Skipping the orphaned-images check: could not diff "
                f"against {base_ref!r} (is the base commit fetched? use "
                "fetch-depth: 0). Not falling back to a whole-tree scan."
            )
            return 0
        scope = f"images added since the merge base with {base_ref}"

    result = run(paths, exts, src_exts, ignores, only)
    if result is None:
        print("::error::check-orphaned-images: `git ls-files` failed; is this a git checkout?")
        return 1
    print(
        f"Examined {result.examined} image(s) ({scope}) against "
        f"{result.sources} source file(s)."
    )
    level = "error" if fail else "warning"
    for img in result.orphans:
        print(
            f"::{level} file={img},title=Image used by no page::"
            f"{img} is not referenced by any source file"
        )
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("## Images no source file references\n\n")
            if result.orphans:
                fh.writelines(f"- `{img}`\n" for img in result.orphans)
            else:
                fh.write(f"None among {result.examined} image(s).\n")
    if result.orphans:
        print(
            f"{len(result.orphans)} image(s) referenced by no source file. "
            "Delete each one no page needs, or add it to paths-ignore if it is "
            "used in a way a source-tree search cannot see."
        )
        return 1 if fail else 0
    print("No orphaned images.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
