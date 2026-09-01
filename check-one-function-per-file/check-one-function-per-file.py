#!/usr/bin/env python3
"""Enforce the one-function-definition-per-file rule across repository code files.

Scans code files (R, Python, Shell, JavaScript, TypeScript, Julia) to ensure
that each file defines at most one top-level function, helping keep code modular,
searchable, and cleanly diffable.

Files can opt out by including an opt-out comment directive:
  # check-one-function-per-file: allow-multiple
  # check-one-function-per-file: opt-out
  # allow-multiple-functions
  // check-one-function-per-file: allow-multiple
"""

import ast
import fnmatch
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

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
    """Check if the file content contains an opt-out comment directive."""
    if custom_marker and custom_marker.strip() and custom_marker.strip() in content:
        return True

    for pat in OPT_OUT_PATTERNS:
        if pat.search(content):
            return True

    return False


def strip_strings_and_comments(line: str, comment_char: str = "#") -> str:
    """Strip quoted strings first, then comments, to prevent corrupting braces/quotes."""
    clean = re.sub(r'"(?:\\.|[^"\\])*"', '""', line)
    clean = re.sub(r"'(?:\\.|[^'\\])*'", "''", clean)
    clean = re.sub(r"`(?:\\.|[^`\\])*`", "``", clean)
    if comment_char == "//":
        clean = clean.split("//", 1)[0]
    else:
        clean = clean.split(comment_char, 1)[0]
    return clean


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


def extract_r_functions(content: str) -> List[Tuple[str, int]]:
    """Extract top-level function definitions from R code."""
    functions = []
    lines = content.splitlines()
    brace_depth = 0

    # Matches: func_name <- function( or `func_name` = function( or func_name <- \(x) (R 4.1+ shorthand)
    func_pattern = re.compile(
        r"^\s*(?:(?:`([^`]+)`)|([a-zA-Z0-9_.]+))\s*(?:<-|=|<<-)\s*(?:function|\\)\s*\(",
    )

    for lineno, line in enumerate(lines, start=1):
        clean_code = strip_strings_and_comments(line, comment_char="#")

        if brace_depth == 0:
            m = func_pattern.match(clean_code)
            if m:
                name = m.group(1) or m.group(2)
                functions.append((name, lineno))

        brace_depth += clean_code.count("{") - clean_code.count("}")
        if brace_depth < 0:
            brace_depth = 0

    return functions


def extract_shell_functions(content: str) -> List[Tuple[str, int]]:
    """Extract top-level function declarations from Shell/Bash code."""
    functions = []
    lines = content.splitlines()
    brace_depth = 0

    func_pat1 = re.compile(r"^\s*function\s+([a-zA-Z0-9_:-]+)(?:\s*\(\s*\))?\s*(?:\{)?")
    func_pat2 = re.compile(r"^\s*([a-zA-Z0-9_:-]+)\s*\(\s*\)\s*(?:\{)?")

    for lineno, line in enumerate(lines, start=1):
        clean_code = strip_strings_and_comments(line, comment_char="#")

        if brace_depth == 0:
            m1 = func_pat1.match(clean_code)
            m2 = func_pat2.match(clean_code)
            if m1:
                functions.append((m1.group(1), lineno))
            elif m2:
                name = m2.group(1)
                if name not in ("if", "then", "else", "elif", "fi", "case", "esac", "for", "while", "until", "do", "done"):
                    functions.append((name, lineno))

        brace_depth += clean_code.count("{") - clean_code.count("}")
        if brace_depth < 0:
            brace_depth = 0

    return functions


def extract_js_ts_functions(content: str) -> List[Tuple[str, int]]:
    """Extract top-level function declarations from JavaScript / TypeScript code."""
    functions = []
    lines = content.splitlines()
    brace_depth = 0

    func_pat1 = re.compile(r"^\s*(?:export\s+(?:default\s+)?)?function\s*\*?\s*([a-zA-Z0-9_$]+)\s*\(")
    func_pat2 = re.compile(
        r"^\s*(?:export\s+)?(?:const|let|var)\s+([a-zA-Z0-9_$]+)(?:\s*:\s*[^=]+)?\s*=\s*(?:async\s+)?(?:<[^>]*>\s*)?(?:(?:\([^)]*\)|[a-zA-Z0-9_$]+)(?:\s*:\s*[^=]+)?\s*=>|function\s*\*?\s*\()"
    )

    for lineno, line in enumerate(lines, start=1):
        clean_code = strip_strings_and_comments(line, comment_char="//")

        if brace_depth == 0:
            m1 = func_pat1.match(clean_code)
            m2 = func_pat2.match(clean_code)
            if m1:
                functions.append((m1.group(1), lineno))
            elif m2:
                functions.append((m2.group(1), lineno))

        brace_depth += clean_code.count("{") - clean_code.count("}")
        if brace_depth < 0:
            brace_depth = 0

    return functions


def extract_julia_functions(content: str) -> List[Tuple[str, int]]:
    """Extract top-level function definitions from Julia code."""
    functions = []
    lines = content.splitlines()

    func_pat1 = re.compile(r"^\s*function\s+([a-zA-Z0-9_!]+)\s*\(")
    func_pat2 = re.compile(r"^([a-zA-Z0-9_!]+)\([^)]*\)\s*=")

    for lineno, line in enumerate(lines, start=1):
        clean_code = strip_strings_and_comments(line, comment_char="#")
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


def check_repository(
    target_path: Path,
    extensions: Set[str],
    paths_ignore: List[str],
    custom_opt_out: Optional[str] = None,
) -> Dict[Path, List[Tuple[str, int]]]:
    """Scan directory and return mapping of violating files to their distinct function definitions."""
    violations: Dict[Path, List[Tuple[str, int]]] = {}

    if target_path.is_file():
        files_to_check = [target_path]
        root_dir = target_path.parent
    else:
        root_dir = target_path
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
        # Deduplicate multiple methods / overloads by distinct function name
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
    extensions_str = os.environ.get("INPUT_EXTENSIONS") or os.environ.get("EXTENSIONS") or ""
    ignore_str = os.environ.get("INPUT_PATHS_IGNORE") or os.environ.get("PATHS_IGNORE") or ""
    opt_out_str = os.environ.get("INPUT_OPT_OUT_COMMENT") or os.environ.get("OPT_OUT_COMMENT") or ""
    fail_str = os.environ.get("INPUT_FAIL") or os.environ.get("FAIL") or "true"

    should_fail = fail_str.lower() in ("true", "1", "yes")
    scan_path = Path(scan_path_str).resolve()
    extensions = parse_extensions(extensions_str)
    paths_ignore = parse_paths_ignore(ignore_str)

    print(f"Scanning '{scan_path}' for one-function-per-file violations...")
    print(f"Extensions: {', '.join(sorted(extensions))}")
    print(f"Paths ignore: {', '.join(paths_ignore)}")

    violations = check_repository(
        scan_path,
        extensions,
        paths_ignore,
        custom_opt_out=opt_out_str if opt_out_str else None,
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
