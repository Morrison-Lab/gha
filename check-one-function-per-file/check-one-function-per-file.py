#!/usr/bin/env python3
"""Enforce the one-function-definition-per-file rule across repository code files.

Scans code files (R, Python, Shell, JavaScript, TypeScript, Julia) to ensure
that each file defines at most one top-level function, helping keep code modular,
searchable, and cleanly diffable.

Existing single-language linters (flake8, lintr, eslint) either lack a dedicated
one-function-per-file rule or require language-specific package installations;
this standalone scanner provides lightweight, cross-ecosystem enforcement without
heavy runtime dependencies.

Files can opt out by including an opt-out comment near the top of the file:
  # check-one-function-per-file: allow-multiple
  # check-one-function-per-file: opt-out
  # allow-multiple-functions
  // check-one-function-per-file: allow-multiple
"""
# check-one-function-per-file: allow-multiple

import ast
import fnmatch
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

DEFAULT_EXTENSIONS = {
    ".R",
    ".r",
    ".py",
    ".sh",
    ".bash",
    ".js",
    ".ts",
    ".mjs",
    ".cjs",
    ".jl",
}

DEFAULT_PATHS_IGNORE = [
    ".git",
    ".github",
    "tests",
    "test",
    "vendor",
    "scratch",
    "_site",
    "node_modules",
    ".pytest_cache",
    ".venv",
    "venv",
]

OPT_OUT_PATTERNS = [
    re.compile(r"check-one-function-per-file:\s*(?:allow-multiple|opt-out|ignore|disable)", re.IGNORECASE),
    re.compile(r"one-function-per-file:\s*(?:allow-multiple|opt-out|ignore|disable)", re.IGNORECASE),
    re.compile(r"allow-multiple-functions", re.IGNORECASE),
]


def parse_extensions(ext_str: str) -> Set[str]:
    """Parse comma- or space-separated extensions into normalized leading-dot format."""
    if not ext_str or not ext_str.strip():
        return DEFAULT_EXTENSIONS
    items = [e.strip() for e in ext_str.replace(",", " ").split() if e.strip()]
    return {e if e.startswith(".") else f".{e}" for e in items}


def parse_paths_ignore(ignore_str: str) -> List[str]:
    """Parse paths-ignore input into a list of normalized directory patterns."""
    if not ignore_str or not ignore_str.strip():
        return list(DEFAULT_PATHS_IGNORE)
    raw_items = [
        item.strip()
        for line in ignore_str.splitlines()
        for item in line.split(",")
        if item.strip()
    ]
    return raw_items


def is_ignored(path: Path, root: Path, ignore_patterns: List[str]) -> bool:
    """Check whether a path matches any ignore pattern relative to root."""
    try:
        rel_path = path.relative_to(root)
    except ValueError:
        rel_path = path
    rel_str = str(rel_path).replace(os.sep, "/")
    parts = rel_path.parts

    for pattern in ignore_patterns:
        pat_clean = pattern.strip().strip("/")
        if not pat_clean:
            continue
        if pat_clean in parts:
            return True
        if (
            fnmatch.fnmatch(rel_str, pat_clean)
            or fnmatch.fnmatch(rel_str, f"{pat_clean}/*")
            or fnmatch.fnmatch(rel_str, f"*/{pat_clean}/*")
            or fnmatch.fnmatch(rel_str, f"*/{pat_clean}")
        ):
            return True
    return False


def is_opted_out(content: str, custom_marker: Optional[str] = None) -> bool:
    """Check if the top comment lines contain an opt-out directive."""
    lines = content.splitlines()[:60]
    in_docstring = False
    docstring_delim = None
    top_comment_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if in_docstring:
            if docstring_delim in stripped:
                in_docstring = False
            continue

        if stripped.startswith(('"""', "'''")):
            delim = '"""' if stripped.startswith('"""') else "'''"
            after_open = stripped[3:]
            if delim not in after_open:
                in_docstring = True
                docstring_delim = delim
            continue

        if (
            stripped.startswith("#")
            or stripped.startswith("//")
            or stripped.startswith("/*")
            or stripped.startswith("*")
            or stripped.startswith("--")
            or stripped.startswith(";")
        ):
            top_comment_lines.append(stripped)
        else:
            # First line of real code reached outside docstrings/comments
            break

    header_text = "\n".join(top_comment_lines)
    if custom_marker and custom_marker.strip() and custom_marker.strip() in header_text:
        return True

    for pat in OPT_OUT_PATTERNS:
        if pat.search(header_text):
            return True

    return False


def extract_python_functions(content: str) -> List[Tuple[str, int]]:
    """Extract top-level function definitions from Python code."""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []

    functions = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append((node.name, node.lineno))
    return functions


def scan_lines_with_depth(
    content: str,
    line_cleaner: Callable[[str], str],
    match_func: Callable[[str], Optional[str]],
    track_parens: bool = False,
) -> List[Tuple[str, int]]:
    """Generic line scanner tracking brace/paren depth to find top-level function definitions."""
    functions = []
    lines = content.splitlines()
    brace_depth = 0
    paren_depth = 0

    for lineno, raw_line in enumerate(lines, start=1):
        clean_code = line_cleaner(raw_line)

        # A top-level function must be outside any enclosing block ({}) or call expression (())
        if brace_depth == 0 and (not track_parens or paren_depth == 0):
            func_name = match_func(clean_code)
            if func_name:
                functions.append((func_name, lineno))

        brace_depth += clean_code.count("{") - clean_code.count("}")
        if brace_depth < 0:
            brace_depth = 0

        if track_parens:
            paren_depth += clean_code.count("(") - clean_code.count(")")
            if paren_depth < 0:
                paren_depth = 0

    return functions


def extract_r_functions(content: str) -> List[Tuple[str, int]]:
    """Extract top-level function definitions from R code."""
    # Matches: func_name <- function( or `func_name` = function( or func_name <- \(x)
    func_pattern = re.compile(
        r"^\s*(?:(?:`([^`]+)`)|([a-zA-Z0-9_.]+))\s*(?:<-|=|<<-)\s*(?:function|\\)\s*\(",
    )

    def clean_r_line(line: str) -> str:
        # Strip string literals while preserving backtick identifiers
        clean = re.sub(r'"(?:\\.|[^"\\])*"', '""', line)
        clean = re.sub(r"'(?:\\.|[^'\\])*'", "''", clean)
        # Strip comments
        clean = clean.split("#", 1)[0]
        return clean

    def match_r(clean_line: str) -> Optional[str]:
        m = func_pattern.match(clean_line)
        if m:
            return m.group(1) or m.group(2)
        return None

    return scan_lines_with_depth(content, clean_r_line, match_r, track_parens=True)


def extract_shell_functions(content: str) -> List[Tuple[str, int]]:
    """Extract top-level function declarations from Shell/Bash code."""
    func_pat1 = re.compile(r"^\s*function\s+([a-zA-Z0-9_:-]+)(?:\s*\(\s*\))?\s*(?:\{)?")
    func_pat2 = re.compile(r"^\s*([a-zA-Z0-9_:-]+)\s*\(\s*\)\s*(?:\{)?")

    def clean_shell_line(line: str) -> str:
        # Protect ${#var...} parameter expansions from being split at #
        protected = re.sub(r"\$\{[^}]*\}", lambda m: m.group(0).replace("#", "_"), line)
        clean = re.sub(r'"(?:\\.|[^"\\])*"', '""', protected)
        clean = re.sub(r"'(?:\\.|[^'\\])*'", "''", clean)
        clean = clean.split("#", 1)[0]
        return clean

    def match_shell(clean_line: str) -> Optional[str]:
        m1 = func_pat1.match(clean_line)
        m2 = func_pat2.match(clean_line)
        if m1:
            return m1.group(1)
        elif m2:
            name = m2.group(1)
            if name not in ("if", "then", "else", "elif", "fi", "case", "esac", "for", "while", "until", "do", "done"):
                return name
        return None

    return scan_lines_with_depth(content, clean_shell_line, match_shell, track_parens=False)


def extract_js_ts_functions(content: str) -> List[Tuple[str, int]]:
    """Extract top-level function declarations from JavaScript / TypeScript code."""
    # First strip multi-line block comments /* ... */ while preserving newline count for accurate line numbers
    no_block_comments = re.sub(r"/\*[\s\S]*?\*/", lambda m: "\n" * m.group(0).count("\n"), content)

    func_pat1 = re.compile(r"^\s*(?:export\s+(?:default\s+)?)?function\s*\*?\s*([a-zA-Z0-9_$]+)\s*\(")
    func_pat2 = re.compile(
        r"^\s*(?:export\s+)?(?:const|let|var)\s+([a-zA-Z0-9_$]+)(?:\s*:\s*[^=]+)?\s*=\s*(?:async\s+)?(?:<[^>]*>\s*)?(?:(?:\([^)]*\)|[a-zA-Z0-9_$]+)(?:\s*:\s*[^=]+)?\s*=>|function\s*\*?\s*\()"
    )

    def clean_js_line(line: str) -> str:
        clean = re.sub(r'"(?:\\.|[^"\\])*"', '""', line)
        clean = re.sub(r"'(?:\\.|[^'\\])*'", "''", clean)
        clean = re.sub(r"`(?:\\.|[^`\\])*`", "``", clean)
        clean = clean.split("//", 1)[0]
        return clean

    def match_js(clean_line: str) -> Optional[str]:
        m1 = func_pat1.match(clean_line)
        m2 = func_pat2.match(clean_line)
        if m1:
            return m1.group(1)
        elif m2:
            return m2.group(1)
        return None

    return scan_lines_with_depth(no_block_comments, clean_js_line, match_js, track_parens=False)


def extract_julia_functions(content: str) -> List[Tuple[str, int]]:
    """Extract top-level function definitions from Julia code."""
    functions = []
    lines = content.splitlines()

    func_pat1 = re.compile(r"^\s*function\s+([a-zA-Z0-9_!]+)\s*\(")
    func_pat2 = re.compile(r"^([a-zA-Z0-9_!]+)\([^)]*\)\s*=")

    for lineno, line in enumerate(lines, start=1):
        clean_code = re.sub(r'"(?:\\.|[^"\\])*"', '""', line).split("#", 1)[0]
        if line.startswith("function ") or line.startswith("function\t"):
            m = func_pat1.match(clean_code)
            if m:
                functions.append((m.group(1), lineno))
        elif not line.startswith(" ") and not line.startswith("\t"):
            m = func_pat2.match(clean_code)
            if m:
                functions.append((m.group(1), lineno))

    return functions


def find_function_definitions(file_path: Path, content: str) -> List[Tuple[str, int]]:
    """Extract top-level function definitions from a file based on extension."""
    ext = file_path.suffix.lower()
    if ext == ".py":
        return extract_python_functions(content)
    elif ext in (".r",):
        return extract_r_functions(content)
    elif ext in (".sh", ".bash"):
        return extract_shell_functions(content)
    elif ext in (".js", ".ts", ".mjs", ".cjs"):
        return extract_js_ts_functions(content)
    elif ext == ".jl":
        return extract_julia_functions(content)
    return []


def get_changed_files(base_ref: str, root_dir: Path) -> Optional[List[Path]]:
    """Retrieve changed/added files from git diff against base_ref."""
    if not base_ref:
        return None
    try:
        cmd = ["git", "diff", "--name-only", "--diff-filter=ACMR", f"{base_ref}...HEAD"]
        res = subprocess.run(cmd, cwd=root_dir, capture_output=True, text=True, check=True)
        paths = [root_dir / line.strip() for line in res.stdout.splitlines() if line.strip()]
        return paths
    except Exception:
        return None


def check_repository(
    target_path: Path,
    extensions: Set[str],
    paths_ignore: List[str],
    custom_opt_out: Optional[str] = None,
    base_ref: Optional[str] = None,
) -> Dict[Path, List[Tuple[str, int]]]:
    """Scan directory and return mapping of violating files to their distinct function definitions."""
    violations: Dict[Path, List[Tuple[str, int]]] = {}

    if target_path.is_file():
        files_to_check = [target_path]
        root_dir = target_path.parent
    else:
        root_dir = target_path
        changed_paths = get_changed_files(base_ref, root_dir) if base_ref else None

        if changed_paths is not None:
            files_to_check = [
                p for p in changed_paths
                if p.is_file()
                and (p.suffix in extensions or p.suffix.lower() in extensions)
                and not is_ignored(p, root_dir, paths_ignore)
            ]
        else:
            files_to_check = []
            for root, dirs, files in os.walk(target_path):
                current_dir = Path(root)
                if is_ignored(current_dir, root_dir, paths_ignore):
                    dirs[:] = []
                    continue
                for f in files:
                    p = current_dir / f
                    if p.suffix in extensions or p.suffix.lower() in extensions:
                        if not is_ignored(p, root_dir, paths_ignore):
                            files_to_check.append(p)

    for file_path in sorted(files_to_check):
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        if is_opted_out(content, custom_opt_out):
            continue

        funcs = find_function_definitions(file_path, content)
        seen_names: Set[str] = set()
        distinct_funcs: List[Tuple[str, int]] = []
        for name, lineno in funcs:
            if name not in seen_names:
                seen_names.add(name)
                distinct_funcs.append((name, lineno))

        if len(distinct_funcs) > 1:
            violations[file_path] = distinct_funcs

    return violations


def main() -> int:
    scan_path_str = os.environ.get("INPUT_PATH") or os.environ.get("SCAN_PATH") or "."
    base_ref = os.environ.get("INPUT_BASE_REF") or os.environ.get("BASE_REF") or ""
    extensions_str = os.environ.get("INPUT_EXTENSIONS") or os.environ.get("EXTENSIONS") or ""
    ignore_str = os.environ.get("INPUT_PATHS_IGNORE") or os.environ.get("PATHS_IGNORE") or ""
    opt_out_str = os.environ.get("INPUT_OPT_OUT_COMMENT") or os.environ.get("OPT_OUT_COMMENT") or ""
    fail_str = os.environ.get("INPUT_FAIL") or os.environ.get("FAIL") or "true"

    should_fail = fail_str.lower() in ("true", "1", "yes")
    scan_path = Path(scan_path_str).resolve()
    extensions = parse_extensions(extensions_str)
    paths_ignore = parse_paths_ignore(ignore_str)

    print(f"Scanning '{scan_path}' for one-function-per-file violations...")
    if base_ref:
        print(f"Diff-scoped against base-ref: {base_ref}")
    print(f"Extensions: {', '.join(sorted(extensions))}")
    print(f"Paths ignore: {', '.join(paths_ignore)}")

    violations = check_repository(
        scan_path,
        extensions,
        paths_ignore,
        custom_opt_out=opt_out_str if opt_out_str else None,
        base_ref=base_ref if base_ref else None,
    )

    if not violations:
        print("✅ No one-function-per-file violations found.")
        return 0

    print(f"\n❌ Found {len(violations)} file(s) with multiple function definitions:\n")
    annotation_level = "error" if should_fail else "warning"

    for file_path, funcs in violations.items():
        try:
            rel = file_path.relative_to(Path.cwd())
        except ValueError:
            rel = file_path
        func_list = ", ".join(f"`{name}` (line {line})" for name, line in funcs)
        print(f"- {rel}: {len(funcs)} functions -> {func_list}")

        first_line = funcs[0][1] if funcs else 1
        msg = (
            f"File '{rel}' defines {len(funcs)} functions ({func_list}). "
            f"Expected at most one function per file. "
            f"To opt out, add '# check-one-function-per-file: allow-multiple' near the top."
        )
        print(f"::{annotation_level} file={rel},line={first_line}::{msg}")

    print("\nTo opt out a specific file that genuinely requires multiple function definitions,")
    print("add one of the following comment lines near the top of the file:")
    print("  # check-one-function-per-file: allow-multiple")
    print("  # check-one-function-per-file: opt-out")
    print("  # allow-multiple-functions")

    if should_fail:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
