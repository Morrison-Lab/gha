#!/usr/bin/env python3
"""
Diff-scoped spellcheck wrapping crate-ci/typos.

spellcheck.yml wraps spelling::spell_check_package(), whose population is an
R package. This check covers the rest: Quarto site pages, CONTRIBUTING.md-
class Markdown, docs/, YAML, code comments, and repositories that are not
R packages. typos is a corrections-list checker rather than a dictionary
checker, so it does not need a curated wordlist.

Design notes:
- **Diff-scoped, by default.** Only lines *added* since ``TYPOS_BASE_REF``
  (a PR's base SHA) are checked, so a corpus's pre-existing typos are not
  reflagged on every unrelated edit. ``typos`` has no wordlist to grow
  into, which is why this matters more here than it does for spellcheck
  (see gha#557). Pass ``TYPOS_BASE_REF=all`` to scan the whole tracked tree.
- **No base_ref to diff against, or the diff can't be computed** (e.g. an
  unset base-ref on a push run, or a shallow clone missing the base
  commit): the check is *skipped* with a warning. There is no whole-tree
  fallback, unlike check-phi -- a whole-tree scan here would defeat the
  point, not just be less precise. Same skip as check-new-line-breaks.
- **Blocking by default** (``TYPOS_FAIL`` defaults to true). Only an
  explicit ``false`` opts out, so a typo in the input cannot quietly
  downgrade the gate to advisory.

Configuration (all via environment variables, set by the composite action):
  TYPOS_BIN_DIR      Directory holding the ``typos`` binary (set by install).
  TYPOS_TARGET       Repository root to check (default: cwd / GITHUB_WORKSPACE).
  TYPOS_CONFIG       Optional path to a typos config file.
  TYPOS_GLOBS        Space-separated git pathspecs (empty => all tracked files).
  TYPOS_PATHS_IGNORE Comma/newline-separated glob patterns to skip.
  TYPOS_BASE_REF     Git ref/SHA to diff against, or ``all`` for the whole tree.
                     Empty => skip the check.
  TYPOS_FAIL         "false" => non-blocking; default "true" => blocking.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

_DEFAULT_FAIL = True
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
# typos --format json exits 2 when it found a typo (crate-ci/typos 1.49.0,
# measured 2026-08-26). Any other non-zero is a tool error and always fails
# the step, whatever `fail` says -- the same split check-secrets draws with
# gitleaks --exit-code 0.
_TYPOS_FOUND_EXIT = 2


class Finding(NamedTuple):
    """One typos finding. ``line`` is None for a filename typo."""

    path: str
    line: Optional[int]
    typo: str
    corrections: Tuple[str, ...]


def _run_git(args: List[str], cwd: Optional[str] = None) -> Optional[str]:
    try:
        return subprocess.run(
            ["git", "-c", "core.quotepath=false", *args],
            capture_output=True,
            check=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _glob_to_regex(pat: str) -> "re.Pattern[str]":
    """Translate a path glob to an anchored regex; supports ``**``, ``*``, ``?``."""
    i, n, out = 0, len(pat), []
    while i < n:
        c = pat[i]
        if c == "*":
            if pat[i : i + 2] == "**":
                i += 2
                if pat[i : i + 1] == "/":
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


def _compile_ignores(patterns: List[str]) -> List["re.Pattern[str]"]:
    compiled = []
    for pat in patterns:
        compiled.append(_glob_to_regex(pat))
        if "*" not in pat and "?" not in pat:
            compiled.append(_glob_to_regex(pat.rstrip("/") + "/**"))
    return compiled


def _ignored(rel: str, ignores: List["re.Pattern[str]"]) -> bool:
    return any(r.match(rel) for r in ignores)


def _split_list(value: str) -> List[str]:
    return [tok.strip() for tok in re.split(r"[,\n]", value or "") if tok.strip()]


def _normalize_path(path: str) -> str:
    # Strip a `./` prefix only. `str.lstrip("./")` would also eat the
    # leading dot of `.github/`, `.gitignore`, `.lintr` -- every hidden
    # path this check exists to cover -- and `(Path / mangled).is_file()`
    # would then drop the file before typos runs.
    path = path.replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path


def _added_line_numbers(
    base_ref: str, pathspecs: List[str], cwd: Optional[str] = None
) -> Optional[Dict[str, Set[int]]]:
    """Return {file: {new-file line numbers added}} vs the merge-base of
    base_ref and HEAD, or None if the diff could not be computed."""
    diff = _run_git(
        ["diff", "--unified=0", "--no-color", f"{base_ref}...HEAD", "--", *pathspecs],
        cwd=cwd,
    )
    if diff is None:
        return None
    result: Dict[str, Set[int]] = {}
    cur_path: Optional[str] = None
    new_lineno = 0
    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            target = raw[4:]
            cur_path = None if target == "/dev/null" else _normalize_path(target[2:])
            if cur_path is not None:
                result.setdefault(cur_path, set())
            continue
        if raw.startswith("@@"):
            m = _HUNK_RE.match(raw)
            new_lineno = int(m.group(1)) if m else 0
            continue
        if raw.startswith("+") and not raw.startswith("+++"):
            if cur_path is not None:
                result[cur_path].add(new_lineno)
            new_lineno += 1
    return result


def _changed_paths(
    base_ref: str, pathspecs: List[str], cwd: Optional[str] = None
) -> Optional[Set[str]]:
    """Paths that appear in the diff, including pure renames / mode changes."""
    out = _run_git(
        ["diff", "--name-only", "-z", f"{base_ref}...HEAD", "--", *pathspecs],
        cwd=cwd,
    )
    if out is None:
        return None
    return {_normalize_path(p) for p in out.split("\0") if p}


def _tracked_files(pathspecs: List[str], cwd: Optional[str] = None) -> Optional[List[str]]:
    out = _run_git(["ls-files", "-z", "--", *pathspecs], cwd=cwd)
    if out is None:
        return None
    return [_normalize_path(p) for p in out.split("\0") if p]


def _env_fail() -> bool:
    """Fail-closed: only an explicit 'false' (trimmed, case-insensitive) opts out.

    Unset/missing uses ``_DEFAULT_FAIL``. An empty value is not unset --
    it is a value other than ``false``, so it still blocks.
    """
    raw = os.environ.get("TYPOS_FAIL")
    if raw is None:
        return _DEFAULT_FAIL
    normalized = "".join(raw.split()).lower()
    return normalized != "false"


def _typos_bin() -> Optional[str]:
    bin_dir = os.environ.get("TYPOS_BIN_DIR", "").strip()
    if bin_dir:
        candidate = Path(bin_dir) / "typos"
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
        return None
    return None


def _parse_jsonl(raw: str) -> List[Finding]:
    findings: List[Finding] = []
    for lineno, line in enumerate(raw.splitlines(), start=1):
        text = line.strip()
        if not text:
            continue
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"typos JSONL line {lineno} is not JSON: {exc}"
            ) from exc
        if obj.get("type") != "typo":
            continue
        path = _normalize_path(str(obj.get("path") or ""))
        if not path:
            continue
        typo = str(obj.get("typo") or "")
        corrections = tuple(str(c) for c in (obj.get("corrections") or []) if c)
        line_num = obj.get("line_num")
        line: Optional[int]
        if line_num is None:
            line = None
        else:
            try:
                line = int(line_num)
            except (TypeError, ValueError):
                line = None
        findings.append(Finding(path=path, line=line, typo=typo, corrections=corrections))
    return findings


def _in_scope(
    finding: Finding,
    whole_tree: bool,
    added: Dict[str, Set[int]],
    changed: Set[str],
) -> bool:
    if whole_tree:
        return True
    if finding.line is None:
        # Filename typo: no line_num (crate-ci/typos 1.49.0, measured
        # 2026-08-26). File-level, so any path the diff names is in scope.
        return finding.path in changed
    return finding.line in added.get(finding.path, set())


def _annotation_message(finding: Finding) -> str:
    typo = finding.typo or "(unknown)"
    if finding.corrections:
        joined = ", ".join(f"'{c}'" for c in finding.corrections)
        body = f"check-typos: '{typo}' should be {joined}"
    else:
        body = f"check-typos: '{typo}' looks like a typo"
    # GitHub annotations treat % / CR / LF as encoding; keep the body one line.
    return body.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _write_summary(findings: List[Finding], whole_tree: bool, base_ref: str) -> None:
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary:
        return
    scope = "whole tracked tree" if whole_tree else f"lines added since {base_ref[:12]}"
    lines = [
        "### check-typos",
        "",
        f"{len(findings)} typo(s) in the {scope}.",
        "",
        "| File | Line | Typo | Corrections |",
        "| --- | --- | --- | --- |",
    ]
    for finding in findings:
        line = str(finding.line) if finding.line is not None else "(filename)"
        corrections = ", ".join(finding.corrections) if finding.corrections else ""
        lines.append(
            f"| `{finding.path}` | {line} | `{finding.typo}` | {corrections} |"
        )
    lines.extend(
        [
            "",
            "typos is a corrections-list checker: a hit is a known misspelling,",
            "not a word missing from a dictionary. Suppress a false positive in",
            "a `_typos.toml` (or `typos.toml` / `.typos.toml`) at the repository",
            "root -- see https://github.com/crate-ci/typos -- or skip the path",
            "with the `paths-ignore` input.",
            "",
        ]
    )
    with open(summary, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def _run_typos(
    typos: str,
    files: List[str],
    config: str,
    excludes: List[str],
    cwd: str,
) -> Tuple[str, int]:
    """Return (stdout, exit_code). Raises RuntimeError on a tool error."""
    if not files:
        return "", 0
    cmd = [typos, "--format", "json", "--color", "never", "--force-exclude"]
    if config:
        cmd.extend(["--config", config])
    for glob in excludes:
        cmd.extend(["--exclude", glob])
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".txt",
        delete=False,
        dir=os.environ.get("RUNNER_TEMP") or None,
    ) as handle:
        handle.write("\n".join(files))
        if files:
            handle.write("\n")
        list_path = handle.name
    try:
        cmd.extend(["--file-list", list_path])
        proc = subprocess.run(
            cmd,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
        )
    finally:
        try:
            os.unlink(list_path)
        except OSError:
            pass
    if proc.returncode not in (0, _TYPOS_FOUND_EXIT):
        detail = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
        raise RuntimeError(detail)
    return proc.stdout, proc.returncode


def collect_findings(
    *,
    base_ref: str,
    globs: List[str],
    ignores: List["re.Pattern[str]"],
    exclude_globs: List[str],
    config: str,
    typos: str,
    cwd: str,
) -> Tuple[List[Finding], bool, int]:
    """Return (in-scope findings, skipped, dropped-count).

    skipped is True when there is no diff to check against -- either
    base_ref was never given, or a base_ref was given but the diff could
    not be computed. Unlike check-phi, there is no whole-tree fallback.
    """
    if not base_ref:
        return [], True, 0
    whole_tree = base_ref == "all"
    pathspecs = globs or ["."]

    if whole_tree:
        tracked = _tracked_files(pathspecs, cwd=cwd)
        if tracked is None:
            return [], True, 0
        files = [
            p
            for p in tracked
            if not _ignored(p, ignores) and (Path(cwd) / p).is_file()
        ]
        added: Dict[str, Set[int]] = {}
        changed: Set[str] = set(files)
    else:
        added = _added_line_numbers(base_ref, pathspecs, cwd=cwd)
        changed_opt = _changed_paths(base_ref, pathspecs, cwd=cwd)
        if added is None or changed_opt is None:
            return [], True, 0
        changed = {p for p in changed_opt if not _ignored(p, ignores)}
        files = sorted(
            p
            for p in set(added) | changed
            if not _ignored(p, ignores) and (Path(cwd) / p).is_file()
        )

    stdout, _rc = _run_typos(typos, files, config, exclude_globs, cwd)
    all_findings = [
        f for f in _parse_jsonl(stdout) if not _ignored(f.path, ignores)
    ]
    in_scope = [
        f for f in all_findings if _in_scope(f, whole_tree, added, changed)
    ]
    dropped = len(all_findings) - len(in_scope)
    return in_scope, False, dropped


def main() -> int:
    target = os.environ.get("TYPOS_TARGET") or os.environ.get("GITHUB_WORKSPACE") or "."
    target_path = Path(target)
    if not target_path.exists():
        print(f"::error::check-typos: path {target!r} does not exist.")
        return 1
    cwd = str(target_path.resolve())

    inside = _run_git(["rev-parse", "--is-inside-work-tree"], cwd=cwd)
    if inside is None or inside.strip() != "true":
        print(f"::error::check-typos: {target!r} is not a git repository.")
        return 1

    typos = _typos_bin()
    if not typos:
        print(
            "::error::check-typos: typos binary not found. "
            "Set TYPOS_BIN_DIR to the directory install-typos.sh wrote."
        )
        return 1

    config = os.environ.get("TYPOS_CONFIG", "").strip()
    if config:
        config_path = Path(cwd) / config
        if not config_path.is_file():
            print(
                f"::error::check-typos: config file {config!r} does not exist "
                f"under {target!r}."
            )
            return 1
        config = str(config_path)

    globs = os.environ.get("TYPOS_GLOBS", "").split()
    exclude_globs = _split_list(os.environ.get("TYPOS_PATHS_IGNORE", ""))
    ignores = _compile_ignores(exclude_globs)
    base_ref = os.environ.get("TYPOS_BASE_REF", "").strip()
    fail = _env_fail()

    try:
        findings, skipped, dropped = collect_findings(
            base_ref=base_ref,
            globs=globs,
            ignores=ignores,
            exclude_globs=exclude_globs,
            config=config,
            typos=typos,
            cwd=cwd,
        )
    except (ValueError, RuntimeError) as exc:
        print(f"::error::check-typos: {exc}")
        return 1

    if skipped:
        reason = (
            f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        )
        print(
            "::warning::Skipping the typos check for this run "
            f"({reason}; not falling back to a whole-tree scan, which would "
            "reflag pre-existing typos)."
        )
        return 0

    whole_tree = base_ref == "all"
    if whole_tree:
        print("Checking for typos (whole tracked tree)\n")
    else:
        print(f"Checking for typos (lines added since {base_ref[:12]})\n")

    if dropped:
        print(
            f"{dropped} finding(s) sit on lines this diff did not add; "
            "ignored (pre-existing drift)."
        )

    if not findings:
        print("No typos found.")
        return 0

    level = "error" if fail else "warning"
    for finding in findings:
        loc = f"file={finding.path}"
        if finding.line is not None:
            loc += f",line={finding.line}"
        print(f"::{level} {loc}::{_annotation_message(finding)}")

    _write_summary(findings, whole_tree, base_ref)

    print(f"\n{len(findings)} typo(s) found.")
    if fail:
        print(f"::error::check-typos: {len(findings)} typo(s) found.")
        return 1
    print(
        f"::warning::check-typos: {len(findings)} typo(s) found "
        "(fail: false, so not blocking)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
