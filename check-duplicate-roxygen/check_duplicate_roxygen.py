#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
"""Check for duplicate roxygen parameter documentation across R code files.

Scans R code files for duplicated roxygen2 `@param` descriptions across functions
and recommends consolidating them using `@inheritParams` or `@inheritDotParams`.

Reusing documentation across functions keeps parameter descriptions synchronized
automatically, prevents documentation drift, and improves maintainability.

Files, blocks, or parameters can opt out using directive comments:
  # check-duplicate-roxygen: allow-duplicates
  # check-duplicate-roxygen: opt-out
  #' check-duplicate-roxygen: allow-duplicates
"""

import argparse
import fnmatch
import os
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

DEFAULT_EXTENSIONS = {".R", ".r"}

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

DEFAULT_MIN_DESC_LENGTH = 10

OPT_OUT_PATTERN = re.compile(
    r"check-duplicate-roxygen:\s*(?:allow-duplicates|allow|opt-out|ignore|disable)",
    re.IGNORECASE,
)

PARAM_REGEX = re.compile(
    r"^#'\s*@param\s+(`[^`]+`|\.\.\.|[A-Za-z0-9._]+)\s*(.*)",
    re.DOTALL,
)

TAG_REGEX = re.compile(r"^#'\s*@([a-zA-Z0-9._]+)")
INHERIT_PARAMS_REGEX = re.compile(r"^#'\s*@inheritParams\s+([A-Za-z0-9._:]+)")
INHERIT_DOT_PARAMS_REGEX = re.compile(r"^#'\s*@inheritDotParams\s+([A-Za-z0-9._:]+)(?:\s+(.*))?")
NAME_TAG_REGEX = re.compile(r"^#'\s*@(?:name|rdname)\s+([A-Za-z0-9._:]+)")


@dataclass
class RoxygenParam:
    name: str
    description: str
    line: int
    opted_out: bool = False


@dataclass
class RoxygenBlock:
    file_path: Path
    start_line: int
    end_line: int
    func_name: Optional[str] = None
    func_args: List[str] = field(default_factory=list)
    params: List[RoxygenParam] = field(default_factory=list)
    inherit_params: List[str] = field(default_factory=list)
    inherit_dot_params: List[Tuple[str, List[str]]] = field(default_factory=list)
    opted_out: bool = False


@dataclass
class DuplicateGroup:
    param_name: str
    description: str
    occurrences: List[Tuple[RoxygenBlock, RoxygenParam]]
    primary_block: Optional[RoxygenBlock] = None
    recommendations: List[str] = field(default_factory=list)


def normalize_whitespace(text: str) -> str:
    """Normalize internal and external whitespace."""
    return re.sub(r"\s+", " ", text).strip()


def parse_extensions(ext_str: str) -> Set[str]:
    """Parse comma- or space-separated extensions into normalized leading-dot format."""
    if not ext_str or not ext_str.strip():
        return DEFAULT_EXTENSIONS
    items = [e.strip() for e in ext_str.replace(",", " ").split() if e.strip()]
    return {e if e.startswith(".") else f".{e}" for e in items}


def parse_paths_ignore(ignore_str: str) -> List[str]:
    """Parse paths-ignore input into a list of normalized directory patterns."""
    if not ignore_str or not ignore_str.strip():
        return DEFAULT_PATHS_IGNORE
    return [p.strip() for p in ignore_str.replace("\n", ",").split(",") if p.strip()]


def is_ignored(file_path: Path, root_dir: Path, paths_ignore: List[str]) -> bool:
    """Check whether a file path matches any of the ignore patterns."""
    try:
        rel_path = file_path.relative_to(root_dir)
    except ValueError:
        rel_path = file_path

    rel_str = str(rel_path).replace("\\", "/")
    parts = rel_path.parts

    for pattern in paths_ignore:
        p = pattern.replace("\\", "/").rstrip("/")
        if p in parts:
            return True
        if fnmatch.fnmatch(rel_str, p) or fnmatch.fnmatch(rel_str, f"*/{p}/*") or fnmatch.fnmatch(rel_str, f"*/{p}"):
            return True
        if any(fnmatch.fnmatch(part, p) for part in parts):
            return True

    return False


def get_diff_modified_files(base_ref: str, root_dir: Path) -> Optional[Set[Path]]:
    """Return set of modified/added files relative to base_ref using git diff."""
    try:
        cmd = ["git", "diff", "--name-only", "--diff-filter=d", base_ref, "HEAD"]
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            cwd=root_dir,
        )
        modified = set()
        for line in result.stdout.splitlines():
            line = line.strip()
            if line:
                modified.add((root_dir / line).resolve())
        return modified
    except Exception as exc:
        print(f"Warning: Failed to obtain git diff against '{base_ref}': {exc}", file=sys.stderr)
        return None


def parse_function_signature(lines: List[str], start_idx: int) -> Tuple[Optional[str], List[str]]:
    """Look ahead from end of roxygen block to detect function name and arguments."""
    idx = start_idx
    n = len(lines)

    # Skip blank lines and plain comments
    while idx < n:
        line = lines[idx].strip()
        if not line or line.startswith("#"):
            idx += 1
            continue
        break

    if idx >= n:
        return None, []

    combined_lines = []
    # Collect up to 20 lines to capture multi-line function declarations
    for j in range(idx, min(n, idx + 20)):
        combined_lines.append(lines[j])
        if "{" in lines[j] or ")" in lines[j]:
            break

    code = "\n".join(combined_lines)

    # Pattern 1: standard function assignment: name <- function(...) or name = function(...)
    fn_match = re.search(
        r"^(?:`([^`]+)`|([A-Za-z0-9._]+))\s*(?:<-|=)\s*(?:function|\\)\s*\((.*?)\)",
        code,
        re.DOTALL | re.MULTILINE,
    )
    if fn_match:
        name = fn_match.group(1) or fn_match.group(2)
        raw_args = fn_match.group(3)
        args = extract_argument_names(raw_args)
        return name, args

    # Pattern 2: setMethod / setGeneric: setMethod("name", ...)
    s4_match = re.search(
        r"^(?:setMethod|setGeneric)\s*\(\s*[\"']([A-Za-z0-9._]+)[\"']",
        code,
        re.MULTILINE,
    )
    if s4_match:
        name = s4_match.group(1)
        # Check if function(...) definition is inside
        fn_inside = re.search(r"(?:function|\\)\s*\((.*?)\)", code, re.DOTALL)
        args = extract_argument_names(fn_inside.group(1)) if fn_inside else []
        return name, args

    return None, []


def extract_argument_names(raw_args: str) -> List[str]:
    """Parse comma-separated argument names from function parameter list."""
    if not raw_args or not raw_args.strip():
        return []

    args: List[str] = []
    paren_depth = 0
    bracket_depth = 0
    brace_depth = 0
    in_quote = None
    current_token: List[str] = []

    for c in raw_args:
        if in_quote:
            current_token.append(c)
            if c == in_quote:
                in_quote = None
            continue

        if c in ('"', "'", "`"):
            in_quote = c
            current_token.append(c)
            continue

        if c == "(":
            paren_depth += 1
            current_token.append(c)
        elif c == ")":
            paren_depth = max(0, paren_depth - 1)
            current_token.append(c)
        elif c == "[":
            bracket_depth += 1
            current_token.append(c)
        elif c == "]":
            bracket_depth = max(0, bracket_depth - 1)
            current_token.append(c)
        elif c == "{":
            brace_depth += 1
            current_token.append(c)
        elif c == "}":
            brace_depth = max(0, brace_depth - 1)
            current_token.append(c)
        elif c == "," and paren_depth == 0 and bracket_depth == 0 and brace_depth == 0:
            arg_str = "".join(current_token).strip()
            if arg_str:
                args.append(parse_single_arg_name(arg_str))
            current_token = []
        else:
            current_token.append(c)

    if current_token:
        arg_str = "".join(current_token).strip()
        if arg_str:
            args.append(parse_single_arg_name(arg_str))

    return args


def parse_single_arg_name(arg_str: str) -> str:
    """Extract argument name from single parameter entry (e.g. `x = 10` -> `x`)."""
    if "=" in arg_str:
        arg_name = arg_str.split("=", 1)[0].strip()
    else:
        arg_name = arg_str.strip()
    return arg_name.strip("`'\"")


def parse_roxygen_blocks(file_path: Path, content: str) -> List[RoxygenBlock]:
    """Parse all roxygen blocks and their associated function metadata from an R file."""
    lines = content.splitlines()
    blocks: List[RoxygenBlock] = []

    # File-level opt out check
    file_opted_out = False
    for line in lines[:20]:
        if OPT_OUT_PATTERN.search(line):
            file_opted_out = True
            break

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("#'"):
            start_line = i + 1
            block_lines = []
            while i < n and lines[i].strip().startswith("#'"):
                block_lines.append((i + 1, lines[i].strip()))
                i += 1
            end_line = i

            block = parse_single_roxygen_block(file_path, start_line, end_line, block_lines)
            if file_opted_out:
                block.opted_out = True

            # Extract associated function name and signature
            func_name, func_args = parse_function_signature(lines, end_line)
            if func_name:
                block.func_name = func_name
                block.func_args = func_args

            blocks.append(block)
        else:
            i += 1

    return blocks


def parse_single_roxygen_block(
    file_path: Path,
    start_line: int,
    end_line: int,
    block_lines: List[Tuple[int, str]],
) -> RoxygenBlock:
    """Parse tags, parameters, and inheritance directives inside a roxygen block."""
    block = RoxygenBlock(file_path=file_path, start_line=start_line, end_line=end_line)

    current_param: Optional[RoxygenParam] = None
    desc_lines: List[str] = []

    def flush_current_param():
        nonlocal current_param, desc_lines
        if current_param is not None:
            full_desc = " ".join(desc_lines)
            current_param.description = normalize_whitespace(full_desc)
            block.params.append(current_param)
            current_param = None
            desc_lines = []

    for line_num, line_str in block_lines:
        if OPT_OUT_PATTERN.search(line_str):
            block.opted_out = True

        inherit_m = INHERIT_PARAMS_REGEX.match(line_str)
        if inherit_m:
            flush_current_param()
            block.inherit_params.append(inherit_m.group(1))
            continue

        dot_inherit_m = INHERIT_DOT_PARAMS_REGEX.match(line_str)
        if dot_inherit_m:
            flush_current_param()
            src = dot_inherit_m.group(1)
            raw_args = dot_inherit_m.group(2) or ""
            args = [a.strip("` ") for a in raw_args.split() if a.strip()]
            block.inherit_dot_params.append((src, args))
            continue

        name_tag_m = NAME_TAG_REGEX.match(line_str)
        if name_tag_m and not block.func_name:
            block.func_name = name_tag_m.group(1)

        param_m = PARAM_REGEX.match(line_str)
        if param_m:
            flush_current_param()
            raw_name = param_m.group(1)
            clean_name = raw_name.strip("`")
            initial_desc = param_m.group(2).strip()
            param_opt_out = bool(OPT_OUT_PATTERN.search(line_str))
            current_param = RoxygenParam(
                name=clean_name,
                description="",
                line=line_num,
                opted_out=param_opt_out,
            )
            desc_lines = [initial_desc] if initial_desc else []
            continue

        if current_param is not None:
            # Check if this line introduces another tag
            if TAG_REGEX.match(line_str):
                flush_current_param()
            else:
                # Continuation of current parameter description
                continuation = re.sub(r"^#'\s?", "", line_str).strip()
                if continuation:
                    desc_lines.append(continuation)

    flush_current_param()
    return block


def find_duplicate_roxygen(
    root_path: Path,
    extensions: Set[str],
    paths_ignore: List[str],
    min_desc_length: int = DEFAULT_MIN_DESC_LENGTH,
    base_ref: Optional[str] = None,
) -> List[DuplicateGroup]:
    """Scan repository R files and identify duplicated roxygen parameter descriptions."""
    diff_modified: Optional[Set[Path]] = None
    if base_ref:
        diff_modified = get_diff_modified_files(base_ref, root_path)

    all_blocks: List[RoxygenBlock] = []

    normalized_extensions = {
        e.lower() if e.startswith(".") else f".{e.lower()}" for e in extensions
    }

    if root_path.is_file():
        candidate_files = [root_path]
    else:
        candidate_files = []
        for p in root_path.rglob("*"):
            if p.is_file() and p.suffix.lower() in normalized_extensions:
                if not is_ignored(p, root_path, paths_ignore):
                    candidate_files.append(p)

    for file_path in sorted(candidate_files):
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            print(f"Warning: Could not read file '{file_path}': {exc}", file=sys.stderr)
            continue

        file_blocks = parse_roxygen_blocks(file_path, content)
        all_blocks.extend(file_blocks)

    # Group parameters by (param_name, normalized_description)
    param_map: Dict[Tuple[str, str], List[Tuple[RoxygenBlock, RoxygenParam]]] = defaultdict(list)

    for block in all_blocks:
        if block.opted_out:
            continue
        for param in block.params:
            if param.opted_out:
                continue
            if len(param.description) < min_desc_length:
                continue
            key = (param.name, param.description)
            param_map[key].append((block, param))

    duplicate_groups: List[DuplicateGroup] = []

    for (param_name, desc), occurrences in param_map.items():
        if len(occurrences) <= 1:
            continue

        # If all occurrences come from the exact same function/block, still flag if multiple
        distinct_funcs = {
            (b.file_path, b.func_name or f"line_{b.start_line}") for b, _ in occurrences
        }

        # Diff-scoping check: at least one occurrence must reside in a modified/added file
        if diff_modified is not None:
            has_modified = any(b.file_path.resolve() in diff_modified for b, _ in occurrences)
            if not has_modified:
                continue

        # Determine primary/canonical block
        # Prefer:
        # 1. Block with matching argument in func_args (concrete signature)
        # 2. Block without '...' in func_args
        # 3. Block with most parameters documented
        # 4. Earliest alphabetical file, earliest line
        def block_priority(item: Tuple[RoxygenBlock, RoxygenParam]):
            b, p = item
            has_exact_arg = 1 if param_name in b.func_args else 0
            has_dot_dot_dot = 1 if "..." in b.func_args else 0
            num_params = len(b.params)
            return (has_exact_arg, -has_dot_dot_dot, num_params, -b.start_line)

        sorted_occurrences = sorted(occurrences, key=block_priority, reverse=True)
        primary_block = sorted_occurrences[0][0]
        primary_name = primary_block.func_name or f"`{primary_block.file_path.name}:{primary_block.start_line}`"

        recommendations: List[str] = []
        for b, p in sorted_occurrences:
            if b is primary_block:
                continue

            target_name = b.func_name or f"`{b.file_path.name}:{b.start_line}`"
            target_loc = f"{b.file_path.name}:{p.line}"

            # Check if target already inherits from primary
            if primary_block.func_name and primary_block.func_name in b.inherit_params:
                rec = (
                    f"- {target_name} ({target_loc}): Remove redundant '@param {param_name}' "
                    f"(already inherited via '@inheritParams {primary_block.func_name}')."
                )
            elif primary_block.func_name and param_name not in b.func_args and "..." in b.func_args:
                rec = (
                    f"- {target_name} ({target_loc}): Function accepts '...' and forwards to '{primary_name}'. "
                    f"Consolidate by replacing '@param {param_name}' with '@inheritDotParams {primary_name} {param_name}'."
                )
            elif primary_block.func_name:
                rec = (
                    f"- {target_name} ({target_loc}): Replace duplicate '@param {param_name}' with "
                    f"'@inheritParams {primary_name}'."
                )
            else:
                rec = (
                    f"- {target_name} ({target_loc}): Duplicate of documentation in {primary_name}. "
                    f"Consolidate parameter documentation using '@inheritParams'."
                )
            recommendations.append(rec)

        group = DuplicateGroup(
            param_name=param_name,
            description=desc,
            occurrences=occurrences,
            primary_block=primary_block,
            recommendations=recommendations,
        )
        duplicate_groups.append(group)

    # Sort groups by parameter name then number of occurrences
    duplicate_groups.sort(key=lambda g: (g.param_name, -len(g.occurrences)))
    return duplicate_groups


def print_report(
    groups: List[DuplicateGroup],
    should_fail: bool,
    root_path: Path,
) -> None:
    """Output formatted violation report and GitHub Actions annotations."""
    total_duplicates = sum(len(g.occurrences) for g in groups)
    print(f"\n❌ Found {len(groups)} duplicate roxygen parameter documentation group(s) ({total_duplicates} total occurrences):\n")

    annotation_level = "error" if should_fail else "warning"

    for group in groups:
        primary_name = (
            group.primary_block.func_name
            if group.primary_block and group.primary_block.func_name
            else "primary definition"
        )
        print(f"=== Parameter: @param {group.param_name} ===")
        desc_snippet = (
            group.description[:80] + "..." if len(group.description) > 80 else group.description
        )
        print(f'Description: "{desc_snippet}"')
        print(f"Canonical source: {primary_name} ({len(group.occurrences)} total definitions)")
        print("Occurrences:")
        for b, p in group.occurrences:
            try:
                rel = b.file_path.relative_to(root_path)
            except ValueError:
                rel = b.file_path
            fn = b.func_name or "<anonymous>"
            is_primary = " [primary]" if b is group.primary_block else ""
            print(f"  - {rel}:{p.line} in `{fn}`{is_primary}")

        print("Recommendations:")
        for rec in group.recommendations:
            print(f"  {rec}")
        print()

        # Emit GitHub Actions annotations
        for b, p in group.occurrences:
            if b is group.primary_block and len(group.occurrences) > 1:
                continue
            try:
                rel_path = str(b.file_path.relative_to(Path.cwd())).replace("\\", "/")
            except ValueError:
                rel_path = str(b.file_path).replace("\\", "/")

            msg = (
                f"Duplicate roxygen '@param {group.param_name}' documentation matching '{primary_name}'. "
                f"Consolidate using @inheritParams or @inheritDotParams."
            )
            print(f"::{annotation_level} file={rel_path},line={p.line}::{msg}")

    print("To opt out a file, block, or parameter that intentionally duplicates documentation,")
    print("add one of the following directives:")
    print("  # check-duplicate-roxygen: allow-duplicates")
    print("  #' check-duplicate-roxygen: allow-duplicates")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check for duplicate roxygen parameter documentation across R code files."
    )
    parser.add_argument("path", nargs="?", default=None, help="Target directory or file to scan.")
    parser.add_argument("--base-ref", default=None, help="Git ref to diff against for diff-scoped scan.")
    parser.add_argument("--extensions", default=None, help="Comma-separated file extensions to check.")
    parser.add_argument("--paths-ignore", default=None, help="Comma-separated paths or globs to ignore.")
    parser.add_argument("--min-desc-length", type=int, default=None, help="Minimum parameter description length.")
    parser.add_argument("--fail", default=None, help="Whether to exit with code 1 when duplicates are found.")

    args = parser.parse_args()

    # Resolve from CLI or ENV
    scan_path_str = args.path or os.environ.get("INPUT_PATH") or "."
    base_ref = args.base_ref or os.environ.get("INPUT_BASE_REF") or ""
    extensions_str = args.extensions or os.environ.get("INPUT_EXTENSIONS") or ""
    ignore_str = args.paths_ignore or os.environ.get("INPUT_PATHS_IGNORE") or ""
    min_desc_len = (
        args.min_desc_length
        if args.min_desc_length is not None
        else int(os.environ.get("INPUT_MIN_DESC_LENGTH") or DEFAULT_MIN_DESC_LENGTH)
    )
    fail_str = (
        args.fail
        if args.fail is not None
        else (os.environ.get("INPUT_FAIL") or "true")
    )

    should_fail = str(fail_str).lower() in ("true", "1", "yes")
    scan_path = Path(scan_path_str).resolve()
    extensions = parse_extensions(extensions_str)
    paths_ignore = parse_paths_ignore(ignore_str)

    print(f"Scanning '{scan_path}' for duplicate roxygen parameter documentation...")
    if base_ref:
        print(f"Diff-scoped against base-ref: {base_ref}")
    print(f"Extensions: {', '.join(sorted(extensions))}")
    print(f"Paths ignore: {', '.join(paths_ignore)}")
    print(f"Min description length: {min_desc_len}")

    duplicates = find_duplicate_roxygen(
        scan_path,
        extensions,
        paths_ignore,
        min_desc_length=min_desc_len,
        base_ref=base_ref if base_ref else None,
    )

    if not duplicates:
        print("✅ No duplicate roxygen documentation found.")
        return 0

    print_report(duplicates, should_fail, scan_path)

    if should_fail:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
