#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
"""Check for duplicate or divergent math definitions and theorems across repos/files.

Scans Quarto (.qmd) and Markdown files for mathematical cross-reference divs
(definitions, theorems, lemmas, corollaries, propositions, conjectures, exercises)
and validates consistency across files and sibling repositories:

1. Exact ID Divergence:
   Flags when the same ID (e.g., `#def-variance`) appears in multiple files or repos
   with divergent/inconsistent mathematical content (divergence detection).
   Identical content is treated as shared/canonical.

2. Conceptual / Title Collisions:
   Flags when the same concept (e.g., matching title "Variance") is defined under
   divergent IDs or divergent content across repositories.

3. In-Repo Duplicate IDs:
   Flags when the same ID is defined more than once in the same repository.

Files or divs can opt out using directive comments:
  <!-- check-math-definitions: allow-divergence -->
  <!-- check-math-definitions: opt-out -->
  <!-- check-math-definitions: ignore -->
"""

import argparse
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from difflib import unified_diff
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

DEFAULT_EXTENSIONS = {".qmd", ".md", ".rmd", ".Rmd"}

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

DEFAULT_PREFIXES = [
    "def",
    "thm",
    "lem",
    "cor",
    "prp",
    "cnj",
    "exr",
    "exm",
    "rem",
    "sol",
    "clm",
]

OPT_OUT_PATTERN = re.compile(
    r"<!--\s*check-math-definitions:\s*(?:allow-divergence|allow-duplicates|allow|opt-out|ignore|disable)\s*-->",
    re.IGNORECASE,
)

# Opening div fence: 3 or more colons optionally followed by attributes
# e.g. ::: {#def-variance} or :::: {#thm-bayes .theorem} or ::: {.definition #def-something}
DIV_FENCE_START = re.compile(r"^(?P<fence>:{3,})\s*(?:\{(?P<attrs>[^}]+)\})?\s*$")
DIV_FENCE_END = re.compile(r"^(?P<fence>:{3,})\s*$")

# Math div ID inside attributes: #def-variance, #thm-bayes, etc.
# Prefixes are parameterized, but by default: def, thm, lem, cor, prp, cnj, exr, ...
ID_ATTR_PATTERN = re.compile(r"#([a-zA-Z0-9_-]+)")

CODE_FENCE_PATTERN = re.compile(r"^(`{3,}|~{3,})")


def extract_title_from_heading_line(line: str) -> Optional[str]:
    """Extract clean title concept from a heading or bold label line.

    Supports:
    - "#### Variance" -> "Variance"
    - "### Bayes' Theorem" -> "Bayes' Theorem"
    - "**Definition 1.1** (Variance)" -> "Variance"
    - "**Theorem**: Law of Total Probability" -> "Law of Total Probability"
    """
    stripped = line.strip()
    if not stripped:
        return None

    # Markdown heading: e.g. "#### Variance" or "### Bayes' Theorem"
    m_h = re.match(r"^#{1,6}\s+(.*?)(?:\s*#+)?$", stripped)
    if m_h:
        title = m_h.group(1).strip()
        title = re.sub(r"^[\s(]+|[\s):.]+$", "", title).strip()
        return title if title else None

    # Bold label: e.g. "**Definition 1.1** (Variance)" or "**Definition 1.1**: Variance"
    m_bold = re.match(
        r"^(?:\*\*|__)[^*_]+(?:\*\*|__)\s*(?:[:(]\s*([^)]+?)\s*[):]?|\s*([^*_]+))?$",
        stripped,
    )
    if m_bold:
        concept = m_bold.group(1) or m_bold.group(2)
        if concept:
            concept = concept.strip()
            concept = re.sub(r"^[\s(]+|[\s):.]+$", "", concept).strip()
            return concept if concept else None

    return None


@dataclass
class MathDiv:
    div_id: str
    prefix: str
    title: str
    repo: str
    file_path: str
    start_line: int
    end_line: int
    raw_content: str
    normalized_content: str
    opted_out: bool = False


@dataclass
class DivergenceFinding:
    kind: str  # 'exact_id_divergence', 'title_collision', 'in_repo_duplicate'
    key: str  # div_id or title
    description: str
    occurrences: List[Dict] = field(default_factory=list)
    diff: Optional[str] = None


def normalize_whitespace(text: str) -> str:
    """Normalize internal and external whitespace."""
    return re.sub(r"\s+", " ", text).strip()


def normalize_math_content(raw_text: str) -> str:
    """Normalize math definition content for fair semantic comparison.

    - Strips HTML/markdown comments
    - Normalizes markdown emphasis / formatting markers
    - Collapses internal whitespace
    - Normalizes common LaTeX formatting differences (spacing around operators)
    """
    # Remove comments
    text = re.sub(r"<!--.*?-->", "", raw_text, flags=re.DOTALL)
    # Remove leading markdown heading lines if already extracted as title
    lines = []
    first_non_empty = True
    for line in text.splitlines():
        trimmed = line.strip()
        if not trimmed:
            continue
        if first_non_empty and extract_title_from_heading_line(trimmed):
            first_non_empty = False
            continue
        first_non_empty = False
        lines.append(trimmed)

    content = " ".join(lines)
    # Normalize LaTeX math spaces: e.g. \, \: \; \quad \qquad \!
    content = re.sub(r"\\[,;:!]|\\(?:quad|qquad)\b", " ", content)
    # Collapse multiple whitespace
    content = re.sub(r"\s+", " ", content).strip()
    return content


def extract_title_and_body(
    lines: List[str],
) -> Tuple[str, str]:
    """Extract optional heading title and body content from div lines."""
    title = ""
    body_lines = []
    found_title = False

    for line in lines:
        stripped = line.strip()
        if not found_title:
            if not stripped:
                body_lines.append(line)
                continue
            # If line is an HTML comment, skip it while looking for title heading
            if stripped.startswith("<!--") and stripped.endswith("-->"):
                body_lines.append(line)
                continue
            t = extract_title_from_heading_line(stripped)
            if t:
                title = t
                found_title = True
                continue
            else:
                found_title = True  # first non-comment non-empty line was not a title heading
        body_lines.append(line)

    raw_body = "\n".join(body_lines)
    return title, raw_body


def parse_math_divs_from_text(
    text: str,
    file_path: str,
    repo_name: str,
    allowed_prefixes: Set[str],
) -> List[MathDiv]:
    """Parse Quarto math divs from source text."""
    divs: List[MathDiv] = []
    lines = text.splitlines()

    # Stack of active divs: (fence_str, div_info_dict, line_start, collected_lines)
    stack: List[Tuple[str, Optional[Tuple[str, str, bool]], int, List[str]]] = []

    file_opt_out = bool(OPT_OUT_PATTERN.search(text))
    in_code_block: Optional[str] = None

    for line_idx, line in enumerate(lines, start=1):
        stripped = line.strip()

        # Track code block fences (``` or ~~~)
        fence_match = CODE_FENCE_PATTERN.match(stripped)
        if fence_match:
            fence_chars = fence_match.group(1)
            if in_code_block is None:
                in_code_block = fence_chars
            elif fence_chars.startswith(in_code_block[:3]) and len(fence_chars) >= len(in_code_block):
                in_code_block = None

        if in_code_block is not None:
            # Inside a code block, ::: does not start or close math divs
            if stack:
                for item in stack:
                    if item[1] is not None:
                        item[3].append(line)
            continue

        # Check for start fence
        start_match = DIV_FENCE_START.match(stripped)
        if start_match and start_match.group("attrs"):
            fence = start_match.group("fence")
            attrs = start_match.group("attrs")

            # Search for #id in attributes
            id_match = ID_ATTR_PATTERN.search(attrs)
            div_meta = None
            if id_match:
                full_id = id_match.group(1)
                # Split prefix and slug: e.g. def-variance -> def, variance
                prefix_candidate = full_id.split("-")[0].split("_")[0].split(":")[0]
                if prefix_candidate in allowed_prefixes:
                    opt_out = file_opt_out or bool(OPT_OUT_PATTERN.search(line))
                    div_meta = (full_id, prefix_candidate, opt_out)

            stack.append((fence, div_meta, line_idx, []))
            continue

        # Check for closing fence
        end_match = DIV_FENCE_END.match(stripped)
        if end_match and stack:
            # Check if this closes the innermost div on stack
            fence_len = len(end_match.group("fence"))
            if len(stack[-1][0]) <= fence_len:
                closed_fence, div_meta, start_line, collected = stack.pop()
                if div_meta is not None:
                    div_id, prefix, opt_out = div_meta
                    raw_block = "\n".join(collected)
                    if OPT_OUT_PATTERN.search(raw_block):
                        opt_out = True

                    title, raw_body = extract_title_and_body(collected)
                    norm_content = normalize_math_content(raw_block)

                    divs.append(
                        MathDiv(
                            div_id=div_id,
                            prefix=prefix,
                            title=title,
                            repo=repo_name,
                            file_path=file_path,
                            start_line=start_line,
                            end_line=line_idx,
                            raw_content=raw_block,
                            normalized_content=norm_content,
                            opted_out=opt_out,
                        )
                    )
                continue

        # If inside one or more divs, collect content for all active divs
        if stack:
            for item in stack:
                if item[1] is not None:
                    item[3].append(line)

    return divs


def scan_file(
    path: Path,
    repo_name: str,
    allowed_prefixes: Set[str],
) -> List[MathDiv]:
    """Scan a single file for math divs."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        print(f"::warning file={path}::Could not read file: {exc}", file=sys.stderr)
        return []
    return parse_math_divs_from_text(
        text=text,
        file_path=str(path),
        repo_name=repo_name,
        allowed_prefixes=allowed_prefixes,
    )


def should_ignore_path(rel_path: str, ignore_patterns: List[str]) -> bool:
    """Check if relative path matches any ignore pattern."""
    parts = Path(rel_path).parts
    for pattern in ignore_patterns:
        # Match against full relative path, filename, or any directory part
        if fnmatch.fnmatch(rel_path, pattern):
            return True
        if fnmatch.fnmatch(rel_path, f"*/{pattern}"):
            return True
        if fnmatch.fnmatch(rel_path, f"*/{pattern}/*"):
            return True
        if pattern in parts:
            return True
        for part in parts:
            if fnmatch.fnmatch(part, pattern):
                return True
    return False


def scan_directory(
    root: Path,
    repo_name: str,
    extensions: Set[str],
    ignore_patterns: List[str],
    allowed_prefixes: Set[str],
) -> List[MathDiv]:
    """Scan a directory recursively for math divs."""
    divs: List[MathDiv] = []
    if not root.exists():
        return divs

    if root.is_file():
        if root.suffix.lower() in extensions:
            return scan_file(root, repo_name, allowed_prefixes)
        return []

    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        # Prune ignored directory names in-place
        dirnames[:] = [
            d
            for d in dirnames
            if not should_ignore_path(
                os.path.normpath(os.path.join(rel_dir, d)), ignore_patterns
            )
        ]

        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in extensions:
                continue
            full_path = Path(dirpath) / fname
            rel_file = os.path.normpath(os.path.join(rel_dir, fname))
            if should_ignore_path(rel_file, ignore_patterns):
                continue

            file_divs = scan_file(full_path, repo_name, allowed_prefixes)
            divs.extend(file_divs)

    return divs


def compare_math_definitions(
    all_divs: List[MathDiv],
    check_titles: bool = True,
) -> List[DivergenceFinding]:
    """Analyze collected math divs for divergence and conflicts."""
    findings: List[DivergenceFinding] = []

    # Group by div_id
    by_id: Dict[str, List[MathDiv]] = defaultdict(list)
    for d in all_divs:
        if not d.opted_out:
            by_id[d.div_id].append(d)

    # 1. Exact ID Divergence & In-Repo Duplicates
    for div_id, items in sorted(by_id.items()):
        # Check in-repo duplicates first
        repo_counts: Dict[str, List[MathDiv]] = defaultdict(list)
        for it in items:
            repo_counts[it.repo].append(it)

        for repo, r_items in repo_counts.items():
            if len(r_items) > 1:
                findings.append(
                    DivergenceFinding(
                        kind="in_repo_duplicate",
                        key=div_id,
                        description=(
                            f"Duplicate definition ID '#{div_id}' defined {len(r_items)} times "
                            f"within repository '{repo}'."
                        ),
                        occurrences=[asdict(it) for it in r_items],
                    )
                )

        # Cross-repo or multi-instance comparison
        if len(items) > 1:
            first = items[0]
            divergent = False
            differing_item = None

            for other in items[1:]:
                if first.normalized_content != other.normalized_content:
                    divergent = True
                    differing_item = other
                    break

            if divergent and differing_item is not None:
                # Generate unified diff
                diff_lines = list(
                    unified_diff(
                        first.normalized_content.split(),
                        differing_item.normalized_content.split(),
                        fromfile=f"{first.repo}:{first.file_path}#{first.div_id}",
                        tofile=f"{differing_item.repo}:{differing_item.file_path}#{differing_item.div_id}",
                        lineterm="",
                    )
                )
                diff_str = "\n".join(diff_lines[:30])

                findings.append(
                    DivergenceFinding(
                        kind="exact_id_divergence",
                        key=div_id,
                        description=(
                            f"Definition ID '#{div_id}' is defined with divergent content across repositories/files. "
                            f"Found in {len(items)} places with differing formulations."
                        ),
                        occurrences=[asdict(it) for it in items],
                        diff=diff_str,
                    )
                )

    # 2. Concept / Title Collision (optional stretch goal)
    if check_titles:
        GENERIC_TITLES = {
            "remark", "note", "solution", "proof", "example", "exercise",
            "definition", "theorem", "lemma", "corollary", "proposition",
        }
        by_prefix_and_title: Dict[Tuple[str, str], List[MathDiv]] = defaultdict(list)
        for d in all_divs:
            if not d.opted_out and d.title:
                norm_title = normalize_whitespace(d.title).lower()
                cleaned_title = re.sub(
                    r"^(?:remark|note|solution|proof|example|exercise|definition|theorem|lemma|corollary|proposition)\s*[\d.]*\s*",
                    "",
                    norm_title,
                ).strip()
                if len(cleaned_title) >= 3 and norm_title not in GENERIC_TITLES:
                    by_prefix_and_title[(d.prefix, norm_title)].append(d)

        for (prefix, title_key), items in sorted(by_prefix_and_title.items()):
            distinct_ids = {it.div_id for it in items}
            if len(distinct_ids) > 1:
                # Same concept title under different IDs within the same div type!
                findings.append(
                    DivergenceFinding(
                        kind="title_collision",
                        key=title_key,
                        description=(
                            f"Concept '{items[0].title}' (#{prefix}) is defined under multiple distinct IDs: "
                            f"{', '.join(sorted(distinct_ids))}."
                        ),
                        occurrences=[asdict(it) for it in items],
                    )
                )

    return findings


def clone_github_repos(
    repo_specs: List[str],
    work_dir: Path,
) -> Dict[str, Path]:
    """Clone sibling repositories for cross-repo scanning."""
    cloned_paths: Dict[str, Path] = {}
    gh_token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")

    for spec in repo_specs:
        spec = spec.strip()
        if not spec:
            continue
        repo_name = spec.rstrip("/").split("/")[-1]
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]
        target_dir = work_dir / repo_name

        if spec.startswith(("http://", "https://", "git@")):
            clone_url = spec
        elif "/" in spec:
            clone_url = f"https://github.com/{spec}.git"
            if gh_token:
                clone_url = f"https://x-access-token:{gh_token}@github.com/{spec}.git"
        else:
            clone_url = spec

        print(f"Cloning {spec} into {target_dir}...", file=sys.stderr)
        cmd = ["git", "clone", "--depth", "1", clone_url, str(target_dir)]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            print(
                f"::warning::Failed to clone repository '{spec}': {res.stderr.strip()}",
                file=sys.stderr,
            )
            continue
        cloned_paths[repo_name] = target_dir

    return cloned_paths


def format_report_markdown(
    divs: List[MathDiv],
    findings: List[DivergenceFinding],
) -> str:
    """Format verification report in GitHub Markdown."""
    lines = [
        "## Math Definition & Theorem Check Report",
        "",
        f"- **Total Math Divs Scanned**: {len(divs)}",
        f"- **Total Divergence / Duplication Findings**: {len(findings)}",
        "",
    ]

    if not findings:
        lines.append(
            "✅ **All math definitions, theorems, and concepts are clean and consistent across scanned repositories.**"
        )
        lines.append("")
    else:
        lines.append("### ⚠️ Divergences & Collisions Found")
        lines.append("")
        for f in findings:
            badge = "🚨 Divergence" if f.kind == "exact_id_divergence" else "⚠️ Collision"
            lines.append(f"#### {badge}: `{f.key}` ({f.kind})")
            lines.append(f"{f.description}")
            lines.append("")
            lines.append("| Repository | File | Line | ID | Title |")
            lines.append("|------------|------|------|----|-------|")
            for occ in f.occurrences:
                lines.append(
                    f"| `{occ['repo']}` | `{occ['file_path']}` | {occ['start_line']} | `{occ['div_id']}` | {occ['title'] or '-'} |"
                )
            lines.append("")
            if f.diff:
                lines.append("<details><summary>Content Diff</summary>")
                lines.append("")
                lines.append("```diff")
                lines.append(f.diff)
                lines.append("```")
                lines.append("</details>")
                lines.append("")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check math definitions, theorems, and cross-repo consistency in Quarto sources."
    )
    parser.add_argument(
        "--path",
        default=os.environ.get("INPUT_PATH", "."),
        help="Primary directory or file path to scan.",
    )
    parser.add_argument(
        "--paths",
        default=os.environ.get("INPUT_PATHS", ""),
        help="Comma- or newline-separated list of directories to scan.",
    )
    parser.add_argument(
        "--repos",
        default=os.environ.get("INPUT_REPOS", ""),
        help="Comma- or newline-separated list of GitHub repos (owner/repo) to clone and scan.",
    )
    parser.add_argument(
        "--paths-ignore",
        default=os.environ.get(
            "INPUT_PATHS_IGNORE", ", ".join(DEFAULT_PATHS_IGNORE)
        ),
        help="Comma- or newline-separated list of path patterns to ignore.",
    )
    parser.add_argument(
        "--extensions",
        default=os.environ.get("INPUT_EXTENSIONS", ".qmd, .md, .rmd, .Rmd"),
        help="Comma- or space-separated list of file extensions.",
    )
    parser.add_argument(
        "--prefixes",
        default=os.environ.get("INPUT_PREFIXES", ", ".join(DEFAULT_PREFIXES)),
        help="Comma- or space-separated list of div ID prefixes (e.g. def, thm, lem).",
    )
    parser.add_argument(
        "--check-titles",
        default=os.environ.get("INPUT_CHECK_TITLES", "true"),
        help="Whether to flag matching titles with divergent IDs (true/false).",
    )
    parser.add_argument(
        "--fail",
        default=os.environ.get("INPUT_FAIL", "true"),
        help="Whether to exit with code 1 if divergence is detected (true/false).",
    )
    parser.add_argument(
        "--output-json",
        default=os.environ.get("INPUT_OUTPUT_JSON", ""),
        help="Path to write JSON findings report.",
    )
    parser.add_argument(
        "--output-markdown",
        default=os.environ.get("INPUT_OUTPUT_MARKDOWN", ""),
        help="Path to write Markdown findings report.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    extensions = {
        ext.strip().lower()
        if ext.strip().startswith(".")
        else f".{ext.strip().lower()}"
        for ext in re.split(r"[,;\s]+", args.extensions)
        if ext.strip()
    }

    ignore_patterns = [
        p.strip()
        for p in re.split(r"[,;\n\r]+", args.paths_ignore)
        if p.strip()
    ]

    prefixes = {
        p.strip().lower()
        for p in re.split(r"[,;\s]+", args.prefixes)
        if p.strip()
    }

    check_titles = args.check_titles.strip().lower() in ("true", "1", "yes")
    fail_on_divergence = args.fail.strip().lower() in ("true", "1", "yes")

    all_divs: List[MathDiv] = []
    temp_dir: Optional[Path] = None

    try:
        # 1. Resolve local scan directories
        targets: List[Tuple[str, Path]] = []
        if args.paths.strip():
            raw_paths = [p.strip() for p in re.split(r"[,;\n\r]+", args.paths) if p.strip()]
            for p in raw_paths:
                pth = Path(p).resolve()
                targets.append((pth.name, pth))
        elif args.path.strip():
            pth = Path(args.path).resolve()
            targets.append((pth.name, pth))

        # 2. Resolve remote GitHub repos if specified
        if args.repos.strip():
            repo_list = [r.strip() for r in re.split(r"[,;\n\r]+", args.repos) if r.strip()]
            temp_dir = Path(tempfile.mkdtemp(prefix="check_math_"))
            cloned = clone_github_repos(repo_list, temp_dir)
            for repo_name, repo_path in cloned.items():
                targets.append((repo_name, repo_path))

        print(
            f"Scanning {len(targets)} targets for math definitions with prefixes: {', '.join(sorted(prefixes))}",
            file=sys.stderr,
        )

        # 3. Collect math divs across all targets
        for label, target_path in targets:
            divs = scan_directory(
                root=target_path,
                repo_name=label,
                extensions=extensions,
                ignore_patterns=ignore_patterns,
                allowed_prefixes=prefixes,
            )
            print(f"[{label}] Found {len(divs)} math divs.", file=sys.stderr)
            all_divs.extend(divs)

        # 4. Compare and analyze
        findings = compare_math_definitions(all_divs, check_titles=check_titles)

        # 5. Output results
        report_md = format_report_markdown(all_divs, findings)
        print(report_md)

        # Write to step summary if in GitHub Actions
        step_summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        if step_summary_path:
            try:
                with open(step_summary_path, "a", encoding="utf-8") as f:
                    f.write(report_md + "\n")
            except Exception as e:
                print(f"::warning::Could not write to GITHUB_STEP_SUMMARY: {e}", file=sys.stderr)

        if args.output_markdown:
            try:
                Path(args.output_markdown).write_text(report_md, encoding="utf-8")
            except Exception as e:
                print(f"::warning::Could not write to {args.output_markdown}: {e}", file=sys.stderr)

        if args.output_json:
            try:
                report_data = {
                    "total_divs": len(all_divs),
                    "divs": [asdict(d) for d in all_divs],
                    "findings": [asdict(f) for f in findings],
                }
                Path(args.output_json).write_text(
                    json.dumps(report_data, indent=2), encoding="utf-8"
                )
            except Exception as e:
                print(f"::warning::Could not write to {args.output_json}: {e}", file=sys.stderr)

        # Emit GitHub workflow annotations
        for f in findings:
            first_occ = f.occurrences[0] if f.occurrences else None
            loc = (
                f"file={first_occ['file_path']},line={first_occ['start_line']}::"
                if first_occ
                else ""
            )
            level = "error" if f.kind in ("exact_id_divergence", "in_repo_duplicate") else "warning"
            print(f"::{level} {loc}{f.description}", file=sys.stderr)

        has_errors = any(f.kind in ("exact_id_divergence", "in_repo_duplicate") for f in findings)
        if has_errors and fail_on_divergence:
            print(
                f"\n❌ Failure: math definition divergence or duplicate ID issue(s) found.",
                file=sys.stderr,
            )
            return 1

        print(
            f"\n✅ Success: {len(all_divs)} math definition(s) scanned cleanly.",
            file=sys.stderr,
        )
        return 0

    finally:
        if temp_dir and temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
