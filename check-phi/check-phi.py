#!/usr/bin/env python3
"""
Scan a repository (or just a pull request's added lines) for content that looks
like Protected Health Information (PHI) / personally identifiable identifiers.

This is a *heuristic* tripwire, not a HIPAA compliance tool: it flags patterns
that are very unlikely to belong in source control (Social Security numbers,
medical record numbers, dates of birth, study/participant identifier literals,
PHI column headers in data files) so a
human can review before the data is merged. It is intentionally tuned for high
precision (few false positives) over recall.

Design notes:
- **Values are never printed.** A leaked SSN in a CI log is still a leak, so
  findings report only ``file:line:col`` plus the detector name — never the
  matched text.
- **Diff-scoped by default.** When ``PHI_BASE_REF`` is set (a PR's base SHA),
  only lines *added* by the PR are scanned, so pre-existing fixtures don't
  re-trip the check on every unrelated edit. Otherwise the whole tracked tree
  is scanned (``git ls-files``), which is what runs on ``push``.

Configuration (all via environment variables, set by the composite action):
  PHI_BASE_REF        Git ref/SHA to diff against. Empty => scan whole tree.
  PHI_DETECTORS       Comma list overriding the enabled detector set
                      (choose from: ssn, mrn, dob, csv_phi_header, study_id, phone,
                      email).
  PHI_PATHS_IGNORE    Comma/newline-separated glob patterns to skip.
  PHI_ALLOWLIST_FILE  Path to a file of regexes; a match whose text matches any
                      regex is suppressed. Defaults to .github/phi-allowlist.txt
                      when that file exists.
  PHI_FAIL            "true" (default) => exit 1 on findings; otherwise warn
                      (annotations + summary) but exit 0.

Inline suppression: any line containing the token ``phi-allow`` (e.g. a
``# phi-allow`` trailing comment) is skipped entirely.
"""

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

# Word-boundary match so the pragma "phi-allow" does NOT also fire on lines
# that merely mention "phi-allowlist" (e.g. a path like .github/phi-allowlist.txt
# in a consumer's YAML), which would silently exclude those lines from scanning.
INLINE_PRAGMA_RE = re.compile(r"\bphi-allow\b", re.IGNORECASE)
DEFAULT_ALLOWLIST = ".github/phi-allowlist.txt"
DEFAULT_DETECTORS = ("ssn", "mrn", "dob", "csv_phi_header", "study_id")
CSV_SUFFIXES = (".csv", ".tsv", ".psv")


# ── Individual detectors ────────────────────────────────────────────────────
# Each detector is a callable (path, lineno, line) -> list[(col, message)].
# Detectors must NOT include the matched value in the message.

_SSN_RE = re.compile(r"(?<!\d)(\d{3})-(\d{2})-(\d{4})(?!\d)")


def _valid_ssn(area: str, group: str, serial: str) -> bool:
    """Reject formats the SSA never issues, cutting false positives from
    zip+4, phone fragments, and other dash-grouped numbers."""
    if area in ("000", "666") or area[0] == "9":
        return False
    if group == "00" or serial == "0000":
        return False
    return True


def _detect_ssn(path: str, lineno: int, line: str) -> List[Tuple[int, str]]:
    out = []
    for m in _SSN_RE.finditer(line):
        if _valid_ssn(m.group(1), m.group(2), m.group(3)):
            out.append((m.start() + 1, "Possible US Social Security Number"))
    return out


_MRN_RE = re.compile(
    r"(?i)\b(?:mrn|medical[\s_-]*record(?:[\s_-]*(?:number|no|num|#))?)\b"
    r"\s*[:#=]?\s*\d{5,12}\b"
)


def _detect_mrn(path: str, lineno: int, line: str) -> List[Tuple[int, str]]:
    return [
        (m.start() + 1, "Possible Medical Record Number")
        for m in _MRN_RE.finditer(line)
    ]


_DOB_RE = re.compile(
    r"(?i)\b(?:dob|date[\s_-]*of[\s_-]*birth|birth[\s_-]*date)\b"
    r"\s*[:=]?\s*(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})"
)


def _detect_dob(path: str, lineno: int, line: str) -> List[Tuple[int, str]]:
    return [
        (m.start() + 1, "Possible date of birth")
        for m in _DOB_RE.finditer(line)
    ]


# A study/participant identifier assigned a literal: the one-off debugging
# spot-check, `if StudyID_c=` followed by a quoted id, that survives into
# committed analysis code.
#
# No example id appears in this comment on purpose. An illustrative literal of
# the right shape would satisfy the pattern below, so this file would flag
# itself the moment the selftest runs every detector over the repository.
#
# Keyed on the *variable name*, not on the value's shape, because a study's own
# id format is arbitrary and picking a shape gets it wrong quietly. In the
# exposure this detector was built from, seven distinct values were each ten
# characters and only two were all digits, so a rule keyed on a run of ten
# digits would have reported twelve of forty-five sites and passed over the
# rest.
#
# Precision comes from requiring all three of: an id-suggestive variable name,
# an assignment or comparison operator, and a *quoted* literal of at least eight
# alphanumerics containing at least one digit. An unquoted right-hand side is
# almost always another variable; a short or all-alphabetic literal is almost
# always a category label; and the eight-character floor keeps ordinary tokens
# like "config1" out while still reaching every real id shape seen so far.
#
# Known limits, stated rather than papered over. A redacted placeholder of the
# form STUDYID20 satisfies the pattern, so a repository that pseudonymizes in
# place needs an allowlist entry for its own placeholder shape. And nothing
# here reaches an identifier with no variable name beside it --- a pasted
# `proc print` block listing bare ids passes straight through, exactly as the
# csv_phi_header detector cannot see an unlabeled column.
_STUDY_ID_RE = re.compile(
    # A lookbehind rather than \b: an underscore is a word character, so \b
    # finds no boundary in `base_patient_id` and the name would be skipped.
    r"(?i)(?<![A-Za-z0-9])"
    r"(?:study|subject|participant|patient|member|enrollee|respondent)"
    r"[\s_-]*(?:id|identifier)s?(?:_[a-z0-9]{1,4})?"
    # Optional close of a subscripted column, `df["patient_id"] = ...`.
    r"(?:[\"']\s*\]{1,2})?"
    # `<-` and `<<-` matter as much as `=` here: R and Quarto are the target
    # ecosystem, and `<-` is the dominant assignment form in both.
    r"\s*(?:<<-|<-|!=|==|=|:)\s*"
    r"(['\"])(?=[A-Za-z0-9]*[0-9])[A-Za-z0-9]{8,}\1"
)


def _detect_study_id(path: str, lineno: int, line: str) -> List[Tuple[int, str]]:
    return [
        (m.start() + 1, "Possible study/participant identifier literal")
        for m in _STUDY_ID_RE.finditer(line)
    ]


# US phone (off by default — noisy). Requires separators to avoid matching
# arbitrary 10-digit IDs.
_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\d)"
)


def _detect_phone(path: str, lineno: int, line: str) -> List[Tuple[int, str]]:
    return [
        (m.start() + 1, "Possible phone number")
        for m in _PHONE_RE.finditer(line)
    ]


# Email (off by default — author/maintainer emails are everywhere in code).
_EMAIL_RE = re.compile(r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def _detect_email(path: str, lineno: int, line: str) -> List[Tuple[int, str]]:
    return [
        (m.start() + 1, "Possible email address")
        for m in _EMAIL_RE.finditer(line)
    ]


# PHI-suggestive column headers in delimited data files. Tokens are normalized
# (lowercased, non-alphanumerics stripped) before comparison.
# Deliberately compound/person-anchored forms only: bare "email", "phone", and
# "address" are common in non-PHI CSVs (mailing lists, config, IP/contract
# addresses) and would erode the high-precision design goal. Enable the `phone`
# and `email` line detectors, or extend this set in a fork, if you need them.
_PHI_HEADER_TOKENS = frozenset({
    "ssn", "socialsecurity", "socialsecuritynumber",
    "mrn", "medicalrecordnumber", "medicalrecordno",
    "patientname", "patientid", "patientfirstname", "patientlastname",
    "dateofbirth", "dob", "birthdate",
    "homeaddress", "streetaddress", "mailingaddress",
    "homephone", "phonenumber", "cellphone",
    "emailaddress",
})


def _detect_csv_phi_header(path: str, lineno: int, line: str) -> List[Tuple[int, str]]:
    if lineno != 1 or not path.lower().endswith(CSV_SUFFIXES):
        return []
    delim = {".tsv": "\t", ".psv": "|"}.get(Path(path).suffix.lower(), ",")
    out = []
    col = 1
    for cell in line.rstrip("\n").split(delim):
        token = re.sub(r"[^a-z0-9]", "", cell.lower())
        if token in _PHI_HEADER_TOKENS:
            out.append((col, "PHI-suggestive column header in data file"))
        col += len(cell) + 1
    return out


DETECTORS: Dict[str, Callable[[str, int, str], List[Tuple[int, str]]]] = {
    "ssn": _detect_ssn,
    "mrn": _detect_mrn,
    "dob": _detect_dob,
    "csv_phi_header": _detect_csv_phi_header,
    "study_id": _detect_study_id,
    "phone": _detect_phone,
    "email": _detect_email,
}


# ── Scope resolution ────────────────────────────────────────────────────────

def _run_git(args: List[str]) -> Optional[str]:
    try:
        # Force UTF-8 with errors="replace" rather than relying on the runner
        # locale, so non-ASCII filenames/content in a diff can't raise an
        # uncaught UnicodeDecodeError and abort the scan.
        return subprocess.run(
            ["git", *args], capture_output=True, check=True,
            encoding="utf-8", errors="replace",
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _looks_binary(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            return b"\x00" in f.read(8192)
    except OSError:
        return True


def _glob_to_regex(pat: str) -> "re.Pattern[str]":
    """Translate a path glob to an anchored regex. Supports ``**`` (any number
    of path segments — the recursive form GitHub's native ``paths-ignore``
    users expect), ``*`` (within a single segment), and ``?``. ``fnmatch`` is
    not used because it treats ``**`` as two literal ``*`` (non-recursive)."""
    i, n, out = 0, len(pat), []
    while i < n:
        c = pat[i]
        if c == "*":
            if pat[i:i + 2] == "**":
                i += 2
                if pat[i:i + 1] == "/":
                    out.append("(?:.*/)?")  # **/  => zero or more leading dirs
                    i += 1
                else:
                    out.append(".*")
            else:
                out.append("[^/]*")  # * stays within one path segment
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
        # Bare names (no wildcards) also get an "everything beneath" expansion,
        # so a directory like "docs" skips "docs/x/y.csv". Patterns that already
        # use wildcards keep GitHub paths-ignore semantics — "tests/*" stays a
        # single segment rather than silently becoming recursive.
        if "*" not in pat and "?" not in pat:
            compiled.append(_glob_to_regex(pat.rstrip("/") + "/**"))
    return compiled


def _ignored(rel: str, ignores: List["re.Pattern[str]"]) -> bool:
    return any(r.match(rel) for r in ignores)


def _tracked_files() -> List[str]:
    out = _run_git(["ls-files"])
    if out is not None:
        return [p for p in out.splitlines() if p]
    # Fallback: walk the tree, skipping the git dir.
    files = []
    for root, dirs, names in os.walk("."):
        dirs[:] = [d for d in dirs if d != ".git"]
        for n in names:
            files.append(os.path.relpath(os.path.join(root, n), "."))
    return files


def _scan_lines_all(ignores: List["re.Pattern[str]"]) -> List[Tuple[str, int, str]]:
    """Return (path, lineno, text) for every line of every tracked text file."""
    rows = []
    for rel in _tracked_files():
        if _ignored(rel, ignores):
            continue
        p = Path(rel)
        if not p.is_file() or _looks_binary(p):
            continue
        try:
            with open(p, "r", encoding="utf-8", errors="strict") as f:
                for lineno, text in enumerate(f, start=1):
                    rows.append((rel, lineno, text))
        except (UnicodeDecodeError, OSError):
            continue  # not text we can scan
    return rows


_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def _scan_lines_diff(base_ref: str, ignores: List["re.Pattern[str]"]) -> Optional[List[Tuple[str, int, str]]]:
    """Return (path, lineno, text) for lines *added* relative to base_ref.
    Returns None if the diff could not be computed (caller falls back to all).

    NOTE: the line-number bookkeeping below assumes ``--unified=0`` (no context
    lines, so every non-``+++`` ``+`` line is an addition to count). If the
    context value ever changes, the increment logic must account for context
    lines too."""
    diff = _run_git(["diff", "--unified=0", "--no-color", f"{base_ref}...HEAD"])
    if diff is None:
        return None
    rows: List[Tuple[str, int, str]] = []
    cur_path: Optional[str] = None
    new_lineno = 0
    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            target = raw[4:]
            if target == "/dev/null":
                cur_path = None  # file deleted — nothing added to scan
            else:
                cur_path = target[2:]  # strip "b/"
                # Skip ignored or binary files, for parity with whole-tree
                # scanning. (git already omits "+"-content for binary files, so
                # the binary guard is defensive.)
                if _ignored(cur_path, ignores) or _looks_binary(Path(cur_path)):
                    cur_path = None
            continue
        if raw.startswith("@@"):
            m = _HUNK_RE.match(raw)
            new_lineno = int(m.group(1)) if m else 0
            continue
        if raw.startswith("+") and not raw.startswith("+++"):
            if cur_path is not None:
                rows.append((cur_path, new_lineno, raw[1:] + "\n"))
            new_lineno += 1
    return rows


# ── Allowlisting ────────────────────────────────────────────────────────────

def _load_allowlist(path: str) -> List["re.Pattern[str]"]:
    if not path:
        return []
    if not os.path.isfile(path):
        # main() only assigns the default path when it exists, so reaching here
        # means a consumer pointed allowlist-file at a path that isn't there.
        print(f"::warning::PHI allowlist file '{path}' not found; "
              f"no allowlist applied.")
        return []
    pats = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                pats.append(re.compile(line))
            except re.error as e:
                print(f"::warning::Invalid allowlist regex '{line}': {e}")
    return pats


# ── Main ────────────────────────────────────────────────────────────────────

def _split_list(value: str) -> List[str]:
    return [tok.strip() for tok in re.split(r"[,\n]", value or "") if tok.strip()]


def main() -> int:
    base_ref = os.environ.get("PHI_BASE_REF", "").strip()
    requested = _split_list(os.environ.get("PHI_DETECTORS", ""))
    enabled = requested or list(DEFAULT_DETECTORS)
    unknown = [d for d in enabled if d not in DETECTORS]
    if unknown:
        print(f"::error::Unknown PHI detector(s): {', '.join(unknown)}. "
              f"Valid: {', '.join(DETECTORS)}")
        return 1
    active = [(name, DETECTORS[name]) for name in enabled]

    ignore = _compile_ignores(_split_list(os.environ.get("PHI_PATHS_IGNORE", "")))
    fail = os.environ.get("PHI_FAIL", "true").strip().lower() != "false"

    allowlist_file = os.environ.get("PHI_ALLOWLIST_FILE", "").strip()
    if not allowlist_file and os.path.isfile(DEFAULT_ALLOWLIST):
        allowlist_file = DEFAULT_ALLOWLIST
    allow = _load_allowlist(allowlist_file)

    if base_ref:
        rows = _scan_lines_diff(base_ref, ignore)
        if rows is None:
            print(f"::warning::Could not diff against '{base_ref}'; "
                  f"scanning the whole tree instead.")
            rows = _scan_lines_all(ignore)
            mode = "whole tree (diff unavailable)"
        else:
            mode = f"lines added since {base_ref[:12]}"
    else:
        rows = _scan_lines_all(ignore)
        mode = "whole tree"

    print(f"Scanning for PHI ({mode}); detectors: {', '.join(enabled)}\n")

    level = "error" if fail else "warning"
    hint = ("If this is synthetic/non-PHI, add a 'phi-allow' comment on the "
            f"line or an entry in {allowlist_file or DEFAULT_ALLOWLIST}.")
    # Stream findings as they are discovered (with `python3 -u`) instead of
    # batching, so a large/violation-heavy scan shows progress live rather than
    # appearing stuck; only a count + file-set are kept for the summary.
    total = 0
    files_hit = set()
    for path, lineno, text in rows:
        # The line is the unit of suppression: an inline `phi-allow` pragma or
        # an allowlist regex matching anywhere on the line suppresses *every*
        # detector hit on that line (not just one match). This is intentional —
        # narrow it to per-match only if that model ever proves too coarse.
        if INLINE_PRAGMA_RE.search(text):
            continue
        if allow and any(p.search(text) for p in allow):
            continue
        for name, fn in active:
            for col, message in fn(path, lineno, text):
                # Value deliberately omitted — never echo PHI to the log.
                print(f"::{level} file={path},line={lineno},col={col}::"
                      f"[phi:{name}] {message} (value redacted). {hint}")
                total += 1
                files_hit.add(path)

    if not total:
        print("✓ No PHI-like content detected.")
        return 0

    print(f"\n✗ Found {total} possible PHI item(s) in {len(files_hit)} file(s). "
          f"Values are redacted above; review the listed file:line locations.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
