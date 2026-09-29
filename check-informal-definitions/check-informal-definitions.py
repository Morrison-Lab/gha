#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
"""Flag informal definitions written in running prose instead of Quarto def divs.

The rule this enforces: in content repositories (Quarto books and sites that use
theorem-type cross-reference divs), technical concepts must be formally defined
in dedicated theorem-like definition divs (`::: {#def-...}`), never in running
prose (gha#970, ai-config shared/writing/informal-definitions.md).

Concepts defined only in prose lack stable cross-reference IDs, cannot be cited
downstream, break hyperlink-on-first-mention requirements, and escape consistency
audits.

This check flags:
1. Bolded or emphasized terms followed by defining language ("is", "are",
   "means", "refers to", "is defined as", "\\eqdef", "\\triangleq") outside a
   formal `::: {#def-...}` (or sibling theorem) div.
2. `\\eqdef` or `\\triangleq` used in inline or display math outside a def div.
3. Prose paragraphs or bolded terms directly under a heading titled "Definitions"
   that are not wrapped in formal def divs.
4. Naming sentences ending in "is:" or "are:" immediately preceding display math
   (`$$...$$`) outside a def div.

Opt-out directives:
- Line/block level: `<!-- check-informal-definitions: allow -->` or
  `<!-- check-informal-definitions: ignore -->`
- File level: `<!-- check-informal-definitions: ignore-file -->`

Sections titled "Notation", "Typographic Conventions", or "Symbols" are
recognized as notation guides and exempt from definition requirements.

Scope:
- Whole tree by default (`INFORMAL_DEFS_DIFF_SCOPED` unset or false).
- Diff-scoped on request (`INFORMAL_DEFS_DIFF_SCOPED=true`), evaluating only
  lines added since `INFORMAL_DEFS_BASE_REF` or in a diff file (`--diff`).
"""

import argparse
import fnmatch
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

DEFAULT_GLOBS = "*.qmd"
DEFAULT_PATHS_IGNORE = ".git, .github, tests, test, vendor, scratch, _site, node_modules, .venv, venv"

# Common labels that use bold prefixes but are not concept definitions
COMMON_LABELS = frozenset({
    "note", "warning", "caution", "tip", "important", "example", "remark",
    "definition", "step", "case", "proof", "solution", "answer", "question",
    "summary", "recap", "prerequisite", "prerequisites", "todo", "fixme",
})

# Section headings that describe typographic conventions rather than concept definitions
EXEMPT_SECTION_RE = re.compile(
    r"^#{1,6}\s+(?:notation|typographic\s+conventions?|conventions?|symbols?|glossary\s+of\s+notation)\b",
    re.IGNORECASE,
)

DEFINITIONS_SECTION_RE = re.compile(
    r"^#{1,6}\s+(?:definitions?|key\s+definitions?)\b",
    re.IGNORECASE,
)

ANY_HEADING_RE = re.compile(r"^#{1,6}\s+\S")

FENCE_RE = re.compile(r"^(\s*)(`{3,}|~{3,})")
DIV_FENCE_START = re.compile(r"^(?P<fence>:{3,})\s*(?:\{(?P<attrs>[^}]+)\})?\s*$")
DIV_FENCE_END = re.compile(r"^(?P<fence>:{3,})\s*$")

# Definition or theorem crossref prefixes: def, thm, lem, cor, prp, cnj, exr, exm, rem, sol, clm
THEOREM_DIV_RE = re.compile(r"(?:^|\s)(?:#(?:def|thm|lem|cor|prp|cnj|exr|exm|rem|sol|clm)-|\.(?:definition|theorem|lemma|corollary|proposition))\b")

# Directives
FILE_OPT_OUT_RE = re.compile(
    r"<!--\s*(?:check-informal-definitions|detect-informal-definitions):\s*ignore-file\s*-->",
    re.IGNORECASE,
)
LINE_OPT_OUT_RE = re.compile(
    r"<!--\s*(?:check-informal-definitions|detect-informal-definitions):\s*(?:allow|ignore|opt-out|disable)\s*-->",
    re.IGNORECASE,
)

# Detection Patterns: optionally allow inline math or symbol parenthetical between term and verb
# (e.g. `A **random variable** $X$ is...` or `The **estimator** $\hat{\theta}$ is defined as...`)
BOLD_DEF_RE = re.compile(
    r"(?i)(?:\b(?:A|An|The)\s+)?\*\*(?P<term>[A-Za-z][a-zA-Z0-9 ._-]{1,60})\*\*(?:\s+\$[^\$\n]+\$|\s+\([^)\n]+\))?(?::\s*|\s+)(?P<defining>is\s+(?:defined\s+as|the|a|an)\b|\bis\b|\bare\b|\bmeans\b|\brefers\s+to\b|\\eqdef\b|\\triangleq\b)"
)

BOLD_COLON_DEF_RE = re.compile(
    r"(?i)\*\*(?P<term>[A-Za-z][a-zA-Z0-9 ._-]{1,60})\*\*(?:\s+\$[^\$\n]+\$|\s+\([^)\n]+\))?:\s+(?P<defining>a|an|the|is|refers|means)\b"
)

EQDEF_RE = re.compile(r"\\(?:eqdef|triangleq)\b")
IS_BEFORE_MATH_RE = re.compile(r"(?i)\b(?:is|are):\s*$")


@dataclass(frozen=True)
class Finding:
    file: Path
    line: int
    rule: str
    term: str
    message: str
    snippet: str


def is_label_or_meta(term: str) -> bool:
    t = term.strip().lower()
    if t in COMMON_LABELS:
        return True
    if any(t.startswith(prefix) for prefix in ("fig", "tab", "step ", "case ")):
        return True
    if t.startswith("-"):
        return True
    return False


def scan_file_lines(
    path: Path, lines: Sequence[str], added_lines: Optional[Set[int]] = None
) -> List[Finding]:
    """Scan the lines of a file for informal definitions."""
    findings: List[Finding] = []

    # Check file-level opt-out
    full_text = "\n".join(lines)
    if FILE_OPT_OUT_RE.search(full_text):
        return findings

    in_yaml = False
    in_code_fence = False
    code_fence_char = ""
    code_fence_len = 0
    in_html_comment = False

    div_stack: List[Tuple[int, bool]] = []  # (depth, is_def_or_theorem)
    in_exempt_section = False
    in_definitions_section = False

    for idx, line in enumerate(lines, start=1):
        # 1. Frontmatter
        if idx == 1 and line.strip() == "---":
            in_yaml = True
            continue
        if in_yaml:
            if line.strip() in ("---", "..."):
                in_yaml = False
            continue

        # 2. HTML comments
        if "<!--" in line and "-->" not in line:
            in_html_comment = True
            continue
        if in_html_comment:
            if "-->" in line:
                in_html_comment = False
            continue

        # 3. Code fences
        m_fence = FENCE_RE.match(line)
        if m_fence:
            marker = m_fence.group(2)
            char = marker[0]
            length = len(marker)
            if not in_code_fence:
                in_code_fence = True
                code_fence_char = char
                code_fence_len = length
                continue
            elif char == code_fence_char and length >= code_fence_len:
                in_code_fence = False
                continue

        if in_code_fence:
            continue

        # 4. Heading changes
        if ANY_HEADING_RE.match(line):
            in_exempt_section = bool(EXEMPT_SECTION_RE.match(line))
            in_definitions_section = bool(DEFINITIONS_SECTION_RE.match(line))

        # 5. Div tracking (::: {#def-...} or :::: {#def-...})
        stripped = line.strip()
        m_div_open = DIV_FENCE_START.match(stripped)
        if m_div_open and m_div_open.group("attrs"):
            fence = m_div_open.group("fence")
            attrs = m_div_open.group("attrs")
            is_def = bool(THEOREM_DIV_RE.search(attrs))
            div_stack.append((fence, is_def))
            continue

        m_div_plain = DIV_FENCE_END.match(stripped)
        if m_div_plain:
            fence = m_div_plain.group("fence")
            fence_len = len(fence)
            if div_stack and len(div_stack[-1][0]) <= fence_len:
                div_stack.pop()
                continue
            elif div_stack and any(len(f) == fence_len for f, _ in div_stack):
                while div_stack and len(div_stack[-1][0]) != fence_len:
                    div_stack.pop()
                if div_stack:
                    div_stack.pop()
                continue
            else:
                div_stack.append((fence, False))
                continue

        # Check line-level opt-out
        if LINE_OPT_OUT_RE.search(line):
            continue

        # If inside a formal definition or theorem div, skip
        if any(is_def for _, is_def in div_stack):
            continue

        # If in an exempt section (Notation / Conventions), skip
        if in_exempt_section:
            continue

        # Table rows or markdown formatting rules
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            continue

        # Check if line should be examined under diff scoping
        is_targeted_line = added_lines is None or idx in added_lines

        # Pattern 1: Bold term followed by defining language
        m_bold = BOLD_DEF_RE.search(line)
        if m_bold:
            term = m_bold.group("term")
            if not is_label_or_meta(term):
                if is_targeted_line:
                    findings.append(
                        Finding(
                            file=path,
                            line=idx,
                            rule="bold-prose-definition",
                            term=term,
                            message=f"Concept '**{term}**' is defined in prose rather than in a formal ::: {{#def-...}} div.",
                            snippet=line.strip(),
                        )
                    )
                continue

        m_colon = BOLD_COLON_DEF_RE.search(line)
        if m_colon:
            term = m_colon.group("term")
            if not is_label_or_meta(term):
                if is_targeted_line:
                    findings.append(
                        Finding(
                            file=path,
                            line=idx,
                            rule="bold-colon-definition",
                            term=term,
                            message=f"Concept '**{term}**' is defined in prose with colon definition rather than in a formal ::: {{#def-...}} div.",
                            snippet=line.strip(),
                        )
                    )
                continue

        # Pattern 2: \eqdef or \triangleq outside a def div
        if EQDEF_RE.search(line):
            if is_targeted_line:
                findings.append(
                    Finding(
                        file=path,
                        line=idx,
                        rule="eqdef-outside-div",
                        term="\\eqdef",
                        message="Mathematical definition operator (\\eqdef or \\triangleq) used outside a formal ::: {#def-...} div.",
                        snippet=line.strip(),
                    )
                )
            continue

        # Pattern 3: Heading titled Definitions over prose without def div
        if in_definitions_section and stripped and not stripped.startswith("#"):
            if is_targeted_line:
                # If there's an emphasized term or definition sentence
                m_any_bold = re.search(r"\*\*(?P<term>[A-Za-z][a-zA-Z0-9 ._-]{1,60})\*\*", line)
                if m_any_bold and not is_label_or_meta(m_any_bold.group("term")):
                    findings.append(
                        Finding(
                            file=path,
                            line=idx,
                            rule="definitions-section-prose",
                            term=m_any_bold.group("term"),
                            message=f"Concept '**{m_any_bold.group('term')}**' defined under '### Definitions' heading in prose instead of in a formal ::: {{#def-...}} div.",
                            snippet=line.strip(),
                        )
                    )
                    continue

        # Pattern 4: Naming sentence ending with is: or are: before display math
        if IS_BEFORE_MATH_RE.search(line):
            # Look ahead for next non-blank line
            next_idx = idx
            while next_idx < len(lines):
                next_line = lines[next_idx].strip()
                if not next_line:
                    next_idx += 1
                    continue
                if next_line.startswith("$$"):
                    if is_targeted_line:
                        findings.append(
                            Finding(
                                file=path,
                                line=idx,
                                rule="naming-sentence-display-math",
                                term="is:",
                                message="Naming sentence ending in 'is:'/'are:' immediately before display math outside a formal ::: {#def-...} div.",
                                snippet=line.strip(),
                            )
                        )
                break

    return findings


def get_diff_added_lines(
    base_ref: str, repo_root: Path, pathspecs: Sequence[str]
) -> Optional[Dict[Path, Set[int]]]:
    """Compute mapping of Path -> set of added line numbers since base_ref."""
    # Find merge base
    cmd_mb = ["git", "merge-base", base_ref, "HEAD"]
    res_mb = subprocess.run(
        cmd_mb, cwd=repo_root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    if res_mb.returncode != 0:
        return None
    mb = res_mb.stdout.strip()
    if not mb:
        return None

    # Run git diff -U0 mb
    cmd_diff = ["git", "diff", "-U0", mb, "--"] + list(pathspecs)
    res_diff = subprocess.run(
        cmd_diff, cwd=repo_root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    if res_diff.returncode != 0:
        return None

    added: Dict[Path, Set[int]] = {}
    current_file: Optional[Path] = None

    for line in res_diff.stdout.splitlines():
        if line.startswith("+++ b/"):
            rel_path = line[6:].strip()
            current_file = repo_root / rel_path
            if current_file not in added:
                added[current_file] = set()
        elif line.startswith("@@ ") and current_file is not None:
            # @@ -a,b +c,d @@ or @@ -a +c,d @@ or @@ -a,b +c @@
            m = re.search(r"\+(\d+)(?:,(\d+))?", line)
            if m:
                start = int(m.group(1))
                count = int(m.group(2)) if m.group(2) else 1
                for l in range(start, start + count):
                    added[current_file].add(l)

    return added


def parse_diff_file(diff_path: Path, repo_root: Path) -> Dict[Path, Set[int]]:
    """Parse added line numbers from a saved diff file."""
    added: Dict[Path, Set[int]] = {}
    if not diff_path.is_file():
        return added

    try:
        content = diff_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return added

    current_file: Optional[Path] = None
    for line in content.splitlines():
        if line.startswith("+++ b/"):
            rel_path = line[6:].strip()
            current_file = repo_root / rel_path
            if current_file not in added:
                added[current_file] = set()
        elif line.startswith("@@ ") and current_file is not None:
            m = re.search(r"\+(\d+)(?:,(\d+))?", line)
            if m:
                start = int(m.group(1))
                count = int(m.group(2)) if m.group(2) else 1
                for l in range(start, start + count):
                    added[current_file].add(l)

    return added


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check for technical definitions written in prose rather than Quarto def divs."
    )
    parser.add_argument(
        "--path",
        default=os.getenv("INFORMAL_DEFS_PATH", "."),
        help="Target directory or file path to check.",
    )
    parser.add_argument(
        "--globs",
        default=os.getenv("INFORMAL_DEFS_GLOBS", DEFAULT_GLOBS),
        help="Space-separated file globs to check (default: '*.qmd').",
    )
    parser.add_argument(
        "--paths-ignore",
        default=os.getenv("INFORMAL_DEFS_PATHS_IGNORE", DEFAULT_PATHS_IGNORE),
        help="Comma-separated paths or glob patterns to ignore.",
    )
    parser.add_argument(
        "--fail",
        default=os.getenv("INFORMAL_DEFS_FAIL", "true"),
        help="Whether to exit with non-zero status on findings (default: 'true').",
    )
    parser.add_argument(
        "--diff-scoped",
        default=os.getenv("INFORMAL_DEFS_DIFF_SCOPED", "false"),
        help="Report only lines added in git diff (default: 'false').",
    )
    parser.add_argument(
        "--base-ref",
        default=os.getenv("INFORMAL_DEFS_BASE_REF", ""),
        help="Git base ref for diff-scoped checking.",
    )
    parser.add_argument(
        "--diff",
        default=os.getenv("INFORMAL_DEFS_DIFF_FILE", ""),
        help="Path to unified diff file to scan added lines from.",
    )
    parser.add_argument(
        "--output-markdown",
        default=os.getenv("INFORMAL_DEFS_OUTPUT_MARKDOWN", ""),
        help="Path to write Markdown summary report.",
    )
    parser.add_argument(
        "--output-json",
        default=os.getenv("INFORMAL_DEFS_OUTPUT_JSON", ""),
        help="Path to write JSON findings report.",
    )

    args = parser.parse_args()

    repo_root = Path.cwd()
    target_path = Path(args.path).resolve()
    globs = [g.strip() for g in args.globs.split() if g.strip()]
    ignore_patterns = [
        p.strip() for p in re.split(r"[,\n]+", args.paths_ignore) if p.strip()
    ]
    should_fail = str(args.fail).lower() in ("true", "1", "yes")
    diff_scoped = str(args.diff_scoped).lower() in ("true", "1", "yes")
    base_ref = args.base_ref.strip()
    diff_file = Path(args.diff).resolve() if args.diff.strip() else None

    # Discover target files
    files_to_scan: List[Path] = []
    if target_path.is_file():
        files_to_scan.append(target_path)
    elif target_path.is_dir():
        # List tracked files via git ls-files if git repo, else rglob
        try:
            cmd = ["git", "ls-files"] + globs
            res = subprocess.run(
                cmd, cwd=target_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            if res.returncode == 0:
                for line in res.stdout.splitlines():
                    p = (target_path / line.strip()).resolve()
                    if p.is_file():
                        files_to_scan.append(p)
        except Exception:
            pass

        if not files_to_scan:
            for g in globs:
                for p in target_path.rglob(g):
                    if p.is_file():
                        files_to_scan.append(p.resolve())

    # Filter out ignored paths
    filtered_files: List[Path] = []
    for f in sorted(set(files_to_scan)):
        try:
            rel = f.relative_to(repo_root)
        except ValueError:
            rel = f
        rel_str = str(rel).replace("\\", "/")
        if any(
            fnmatch.fnmatch(rel_str, pat) or fnmatch.fnmatch(f.name, pat)
            or any(part in pat for part in rel.parts)
            for pat in ignore_patterns
        ):
            continue
        filtered_files.append(f)

    # Compute diff-added lines if requested
    added_lines_map: Optional[Dict[Path, Set[int]]] = None
    if diff_file and diff_file.is_file():
        added_lines_map = parse_diff_file(diff_file, repo_root)
    elif diff_scoped:
        if base_ref:
            added_lines_map = get_diff_added_lines(base_ref, repo_root, globs)
            if added_lines_map is None:
                print(
                    f"::warning::check-informal-definitions: Could not compute diff against base-ref '{base_ref}'. Skipping diff-scoped check.",
                    file=sys.stderr,
                )
                return 0
        else:
            print(
                "::warning::check-informal-definitions: diff-scoped requested but no base-ref or diff-file provided. Skipping.",
                file=sys.stderr,
            )
            return 0

    all_findings: List[Finding] = []
    for f in filtered_files:
        added_lines = added_lines_map.get(f) if added_lines_map is not None else None
        if added_lines_map is not None and not added_lines:
            # File had no added lines in diff
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print(f"Warning: could not read {f}: {e}", file=sys.stderr)
            continue
        lines = content.splitlines()
        findings = scan_file_lines(f, lines, added_lines)
        all_findings.extend(findings)

    # Report results
    if all_findings:
        print(f"check-informal-definitions: Found {len(all_findings)} informal definition(s) in prose:\n")
        for f in all_findings:
            try:
                rel = f.file.relative_to(repo_root)
            except ValueError:
                rel = f.file
            rel_str = str(rel).replace("\\", "/")
            print(f"  {rel_str}:{f.line}: [{f.rule}] {f.message}")
            print(f"    Snippet: {f.snippet}\n")
            # GitHub annotation
            severity = "error" if should_fail else "warning"
            print(
                f"::{severity} file={rel_str},line={f.line},title=Informal definition in prose::[{f.rule}] {f.message}"
            )

        if args.output_markdown:
            out_md = Path(args.output_markdown)
            out_md.parent.mkdir(parents=True, exist_ok=True)
            with open(out_md, "w", encoding="utf-8") as mdf:
                mdf.write("### Informal Definitions in Prose\n\n")
                mdf.write(
                    "The following technical concepts appear to be defined in running prose "
                    "rather than inside formal Quarto definition divs (`::: {#def-...}`). "
                    "Every technical concept defined in content repositories must have its own formal "
                    "`::: {#def-...}` div with a worked example.\n\n"
                )
                for f in all_findings:
                    try:
                        rel = f.file.relative_to(repo_root)
                    except ValueError:
                        rel = f.file
                    mdf.write(f"- `{rel}:{f.line}`: **{f.term}** ({f.rule})\n  > {f.snippet}\n")

        if args.output_json:
            import json

            out_json = Path(args.output_json)
            out_json.parent.mkdir(parents=True, exist_ok=True)
            with open(out_json, "w", encoding="utf-8") as jf:
                json.dump(
                    [
                        {
                            "file": str(f.file.relative_to(repo_root) if repo_root in f.file.parents else f.file),
                            "line": f.line,
                            "rule": f.rule,
                            "term": f.term,
                            "message": f.message,
                            "snippet": f.snippet,
                        }
                        for f in all_findings
                    ],
                    jf,
                    indent=2,
                )

        if should_fail:
            return 1
    else:
        print("check-informal-definitions: Clean. No informal definitions found.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
