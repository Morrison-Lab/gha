#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a new bitmap figure, where a script-generated vector graph would do.

Rule (Ezra, 2026-11-21, Morrison-Lab/lds#3086): replace bitmap images with
script-generated vector graphs. A figure drawn by code is saved as SVG (or
PDF), so it stays sharp at any zoom and its text stays text; a scan, a
screenshot or a PNG export does neither.

What a pull request is flagged for:

- **A new bitmap file**: a tracked file the diff adds whose extension is
  ``.png``, ``.jpg``, ``.jpeg``, ``.gif``, ``.bmp``, ``.tif``, ``.tiff`` or
  ``.webp``. A rename is not new. ``paths-ignore`` exempts a directory such as
  ``images/screenshots/``, where a bitmap is the only faithful form.
- **A new reference to a bitmap**: an added Markdown image
  (``![alt](x.png)``), ``<img src="x.png">`` tag or
  ``knitr::include_graphics("x.png")`` whose target has one of those
  extensions, outside code fences and HTML comments. A target that resolves
  into an ignored path is exempt.
- **A raster figure device**: an added ``fig-format: png`` (or ``retina``,
  ``jpeg``), ``dev: png`` (``#| dev:``, ``dev =``, any raster device such as
  ``ragg_png``), or a ``ggsave()`` / ``savefig()`` call writing a bitmap.
  In a markup file only code fences and YAML front matter are read for these,
  so prose quoting ``dev: png`` passes. A path the code computes, a call
  split over lines, or a nested call before the file name is not seen.

``<!-- check-bitmap-figures: allow: reason -->`` with a non-empty reason,
on the flagged line or the line above it, exempts that line, for a photo or
a screenshot.
A new bitmap file is exempt through ``paths-ignore`` only.

Design notes, in the model of ``check-exm-figures``:

- **Diff-scoped.** Only lines and files a diff adds are reported, so existing
  bitmaps are never reflagged; an added line whose exact text was also deleted
  in the same diff is moved, not new.
- **Skip, not fall back.** With no base ref, or when the diff cannot be
  computed, the check skips with a warning. ``CBF_WHOLE_TREE=true`` scans
  every tracked file, which measures how many bitmaps a repository carries.
- **Blocking by default** (``CBF_FAIL`` defaults to true).

Configuration (environment variables, set by the composite action):
  CBF_BASE_REF      Git ref/SHA to diff against. Empty and not whole-tree =>
                    skip the check.
  CBF_GLOBS         Space-separated git pathspecs of text files to scan for
                    references and devices (default: '*.qmd *.Rmd *.md
                    *.yml *.yaml *.R *.py').
  CBF_PATHS_IGNORE  Comma/newline-separated glob patterns: files not scanned,
                    and bitmap files and targets that are allowed.
  CBF_FAIL          "false" => warn only; default "true".
  CBF_WHOLE_TREE    "true" => scan every tracked file in full.
"""

import importlib.util
import os
import posixpath
import re
import sys
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _load_sibling(name: str):
    """Import a sibling check's script, whose directory name has hyphens."""
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, os.pardir, name, name + ".py")
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ods = _load_sibling("check-one-div-per-subfile")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "check-common"))
import diffscope  # noqa: E402
import mdmask  # noqa: E402

DEFAULT_GLOBS = "*.qmd *.Rmd *.md *.yml *.yaml *.R *.py"
_DEFAULT_FAIL = True

MARKUP_EXTS = (".qmd", ".rmd", ".md", ".markdown", ".html")
BITMAP_EXTS = ("png", "jpg", "jpeg", "gif", "bmp", "tif", "tiff", "webp")
_EXT = r"\.(?:" + "|".join(BITMAP_EXTS) + r")"

ADVICE = ("draw the figure with code and save it as SVG (R: the svglite "
          "device; matplotlib: an .svg file or fig-format: svg)")
FILE_ADVICE = (ADVICE + ", or, for a screenshot or photo, keep it under a "
               "path the caller's paths-ignore allows")
LINE_ADVICE = (ADVICE + ", or, for a screenshot or photo, add "
               "<!-- check-bitmap-figures: allow: reason --> on this line "
               "or the one above")

IMAGE_RES = [re.compile(p, re.IGNORECASE) for p in (
    r"!\[[^\]]*\]\(\s*([^)\s<>]+" + _EXT + r")(?=[)\s?#])",
    r"!\[[^\]]*\]\(\s*<([^<>]+" + _EXT + r")(?=[>?#])",
    r"<img\b[^>]*\bsrc\s*=\s*[\"']?([^\"'\s>]+" + _EXT + r")(?=[\"'\s>?#]|$)",
    r"\binclude_graphics\s*\(\s*(?:path\s*=\s*)?[\"']([^\"']+" + _EXT + r")[\"']",
)]
RASTER_DEVICES = r"(?:png|retina|jpe?g|bmp|tiff?|ragg_png|ragg_jpeg|ragg_tiff|CairoPNG|CairoJPEG)"
DEVICE_RES = [re.compile(p) for p in (
    r"^\s*(?:#\|\s*)?fig[-.]format\s*:\s*[\"']?(?:png|retina|jpe?g)\b",
    r"^\s*(?:#\|\s*)?dev\s*:\s*[\"']?" + RASTER_DEVICES + r"\b",
    r"\bdev\s*=\s*[\"']" + RASTER_DEVICES + r"[\"']",
    r"\bggsave\s*\([^)]*[\"'][^\"']+" + _EXT + r"[\"']",
    r"\bsavefig\s*\([^)]*[\"'][^\"']+" + _EXT + r"[\"']",
)]
EXEMPT_RE = re.compile(r"<!--\s*check-bitmap-figures:\s*allow:\s*(?!-->)\S")
# On the line above, the comment exempts only when it stands alone, so an
# allowed image does not also exempt the unrelated image after it.
EXEMPT_ALONE_RE = re.compile(
    r"^\s*<!--\s*check-bitmap-figures:\s*allow:\s*(?!-->)\S.*?-->\s*$")
DEVICE_MESSAGE = ("Raster figure device or bitmap output. "
                  f"Fix: {LINE_ADVICE}")


def exempt(lines: List[str], idx: int) -> bool:
    """Whether line ``idx`` (0-based) carries or follows an allow comment."""
    if EXEMPT_RE.search(lines[idx]):
        return True
    return idx > 0 and bool(EXEMPT_ALONE_RE.match(lines[idx - 1]))


def is_bitmap_path(rel: str) -> bool:
    return rel.lower().endswith(tuple("." + e for e in BITMAP_EXTS))


def resolve_target(source: str, target: str) -> str:
    """A reference's target as a repository path, or the target itself.

    A URL is returned unchanged. A ``/``-rooted path is taken from the
    repository root; any other is joined to the referring file's directory.
    """
    if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE):
        return target
    if target.startswith("/"):
        return posixpath.normpath(target.lstrip("/"))
    return posixpath.normpath(posixpath.join(posixpath.dirname(source), target))


class Finding(NamedTuple):
    path: str
    line: int
    message: str


def scan_lines(rel: str, lines: List[str], keep: Optional[Set[int]],
               ignores: list) -> List[Finding]:
    """Bitmap references and raster devices on kept lines of one file.

    Markdown images, ``<img>`` tags, fences and HTML comments mean something
    only in a markup file; in a script or YAML file every line is read as
    code, for ``include_graphics()`` and the raster devices.
    """
    markup = rel.lower().endswith(MARKUP_EXTS)
    found: List[Finding] = []
    fence: Optional[Tuple[str, int]] = None
    in_comment = False
    front = bool(markup and lines and lines[0].strip() == "---")
    for idx, raw in enumerate(lines):
        n = idx + 1
        text = raw
        if front:
            # YAML front matter is code: devices count, images do not.
            if idx and raw.strip() in ("---", "..."):
                front = False
            if (keep is None or n in keep) and not exempt(lines, idx) \
                    and any(rx.search(raw) for rx in DEVICE_RES):
                found.append(Finding(rel, n, DEVICE_MESSAGE))
            continue
        in_fence = fence is not None
        if markup and fence is None:
            text, in_comment = ods.strip_comments(raw, in_comment)
        m = ods.FENCE_RE.match(text) if markup else None
        if fence is not None:
            if (m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]
                    and not m.group(2).strip()):
                fence = None
        elif m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            fence = (m.group(1)[0], len(m.group(1)))
            in_fence = True
        if keep is not None and n not in keep:
            continue
        if exempt(lines, idx):
            continue
        if not in_fence:
            if markup:
                text = mdmask.mask_code_spans(text)
            for rx in (IMAGE_RES if markup else IMAGE_RES[-1:]):
                for hit in rx.finditer(text):
                    target = resolve_target(rel, hit.group(1))
                    if diffscope.ignored(target, ignores):
                        continue
                    found.append(Finding(rel, n, (
                        f"Reference to the bitmap '{hit.group(1)}'. "
                        f"Fix: {LINE_ADVICE}")))
        # In a markup file a device setting is code only inside a fence;
        # prose that quotes `dev: png` is not one.
        if (in_fence or not markup) and any(rx.search(text) for rx in DEVICE_RES):
            found.append(Finding(rel, n, DEVICE_MESSAGE))
    return found


class Report(NamedTuple):
    findings: List[Finding]
    files: int
    lines: int
    bitmaps: int
    skipped: bool


def run_check(base_ref: str, globs: List[str], ignores: list,
              whole_tree: bool) -> Report:
    wanted: Dict[str, Optional[Set[int]]] = {}
    new_files: List[str] = []
    if whole_tree:
        listed = diffscope.git_paths(["ls-files"])
        scanned = diffscope.git_paths(["ls-files", "--", *globs])
        if listed is None or scanned is None:
            return Report([], 0, 0, 0, True)
        new_files = [p for p in listed if is_bitmap_path(p)]
        for rel in scanned:
            if not diffscope.ignored(rel, ignores):
                wanted[rel] = None
    else:
        if not base_ref:
            return Report([], 0, 0, 0, True)
        base = diffscope.run_git(["merge-base", base_ref, "HEAD"])
        if base is None or not base.strip():
            return Report([], 0, 0, 0, True)
        base = base.strip()
        added_files = diffscope.git_paths(
            ["diff", "--name-only", "--no-ext-diff", "-M", "--diff-filter=A",
             base])
        diff = diffscope.run_git(["diff", "-U0", "--no-color", "--no-ext-diff",
                                  base, "--", *globs])
        if added_files is None or diff is None:
            return Report([], 0, 0, 0, True)
        new_files = [p for p in added_files if is_bitmap_path(p)]
        added, deleted = diffscope.parse_diff(diff)
        for rel, numbered in added.items():
            if diffscope.ignored(rel, ignores):
                continue
            wanted[rel] = {n for n, text in numbered.items()
                           if text.strip() and text not in deleted}

    findings: List[Finding] = []
    bitmaps = 0
    for rel in sorted(new_files):
        bitmaps += 1
        if diffscope.ignored(rel, ignores):
            continue
        verb = "Bitmap file" if whole_tree else "New bitmap file"
        findings.append(Finding(rel, 1, f"{verb} {rel}. Fix: {FILE_ADVICE}"))
    files = lines = 0
    for rel in sorted(wanted):
        content = diffscope.read_lines(rel)
        if content is None:
            continue
        files += 1
        keep = wanted[rel]
        lines += len(content) if keep is None else len(keep)
        findings.extend(scan_lines(rel, content, keep, ignores))
    return Report(findings, files, lines, bitmaps, False)


def main() -> int:
    base_ref = os.environ.get("CBF_BASE_REF", "").strip()
    globs = os.environ.get("CBF_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = diffscope.compile_ignores(
        diffscope.split_list(os.environ.get("CBF_PATHS_IGNORE", "")))
    fail = diffscope.env_flag("CBF_FAIL", _DEFAULT_FAIL)
    whole_tree = diffscope.env_flag("CBF_WHOLE_TREE", False)

    report = run_check(base_ref, globs, ignores, whole_tree)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        level = "::warning::" if base_ref else ""
        print(
            f"{level}Skipping the bitmap-figure check for this run "
            f"({reason}; not falling back to a whole-tree scan, which would "
            f"reflag every bitmap the repository already carries)."
        )
        return 0

    scope = "whole tree" if whole_tree else f"lines and files added since {base_ref}"
    print(
        f"Examined {report.lines} line(s) across {report.files} file(s) and "
        f"{report.bitmaps} bitmap file(s) (scope: {scope})."
    )
    severity = "error" if fail else "warning"
    for f in report.findings:
        print(f"::{severity} file={f.path},line={f.line}::{f.message}")
    if not report.findings:
        print("No new bitmap figure, bitmap reference or raster device.")
        return 0
    print(f"\n{len(report.findings)} bitmap finding(s).")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
