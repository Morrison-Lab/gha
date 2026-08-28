#!/usr/bin/env python3
"""Run automated agentic code reviews, security audits, or test-suite generation

using the Google Antigravity Python SDK (google-antigravity).
"""

import argparse
import asyncio
import json
import os
import random
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from google.antigravity import Agent, LocalAgentConfig, CapabilitiesConfig, BuiltinTools
except ImportError:
    # Fallback / mock support for offline unit testing without SDK installed
    Agent = None
    LocalAgentConfig = None
    CapabilitiesConfig = None
    BuiltinTools = None


LOCATION_GUIDANCE = (
    "\n\nFor line-anchored code findings, include a fenced JSON block at the end of your report formatted as:\n"
    "```json\n"
    "[\n"
    "  {\n"
    '    "path": "relative/path/to/file.ext",\n'
    '    "start_line": 12,\n'
    '    "end_line": 20,\n'
    '    "title": "Short Finding Title",\n'
    '    "body": "Detailed explanation and suggested fix..."\n'
    "  }\n"
    "]\n"
    "```\n"
    "Alternatively, you may include location headers formatted as `**Location:** [path/to/file.ext:L12-L20]`."
)

NOISE_GUIDANCE = (
    "\n\nDo not generate asymptotic noise or hyper-pedantic nitpicks about legacy/EOL runtime compatibility "
    "(assume Python 3.10+; do NOT flag PEP 604 `A | B` union types or `list[T]` generics as issues for Python < 3.10 "
    "unless explicit legacy runtime support is declared). Focus strictly on actionable bugs, security vulnerabilities, "
    "API contract breaks, and performance regressions."
)

MODE_PROMPTS = {
    "code-review": (
        "You are an expert AI code reviewer. Perform a comprehensive, single-pass review of the provided pull request diff. "
        "Report ALL architectural concerns, bugs, edge cases, performance issues, readability improvements, "
        "and missing test coverage at once. Do not withhold or stagger findings across multiple review rounds; "
        "surface every actionable finding and recommendation immediately in this single review. "
        "Provide actionable, constructive feedback with clear code examples where applicable."
        + LOCATION_GUIDANCE
        + NOISE_GUIDANCE
    ),
    "security-audit": (
        "You are a principal security engineer conducting a comprehensive security audit on the pull request diff. "
        "Report ALL OWASP Top 10 vulnerabilities, credential or key leakage, improper input validation, "
        "injection risks, authentication/authorization gaps, and sensitive data (PHI/PII) exposure at once. "
        "Do not stagger security findings across multiple review rounds; surface every finding immediately in a single audit pass. "
        "Classify findings by severity (Critical, High, Medium, Low) and provide defensive remediation guidance."
        + LOCATION_GUIDANCE
        + NOISE_GUIDANCE
    ),
    "test-generation": (
        "You are an automated test engineering agent. Analyze the pull request diff and existing codebase structure. "
        "Generate clean, robust, runnable unit and integration tests covering the new or modified functionality. "
        "Include tests for boundary conditions, unexpected inputs, and failure paths."
    ),
}


def parse_args(args=None):
    parser = argparse.ArgumentParser(
        description="Run Antigravity SDK agentic tasks on PR diffs."
    )
    parser.add_argument(
        "--mode",
        choices=["code-review", "security-audit", "test-generation"],
        default="code-review",
        help="Operational mode for the agent",
    )
    parser.add_argument(
        "--pr-number",
        type=int,
        help="Pull request number (or inferred from GITHUB_REF / event)",
    )
    parser.add_argument(
        "--model",
        default="",
        help="Model override (optional)",
    )
    parser.add_argument(
        "--prompt-addendum",
        default="",
        help="Additional instructions to append to the agent prompt",
    )
    parser.add_argument(
        "--trigger-policy",
        choices=["any", "on-push", "on-request"],
        default="any",
        help="Trigger policy: any (default), on-push (automatic PR updates), or on-request (manual dispatch)",
    )
    parser.add_argument(
        "--post-comment",
        action="store_true",
        help="Post the output as a comment/review on the GitHub PR via gh CLI",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print prompt and diff without executing agent or posting comments",
    )
    parser.add_argument(
        "--fail-on-error",
        action="store_true",
        help="Whether to fail the workflow run if the orchestration engine throws an error",
    )
    parser.add_argument(
        "--max-diff-lines",
        type=int,
        default=2000,
        help="Maximum modified lines allowed in a PR diff before skipping review",
    )
    parser.add_argument(
        "--max-diff-files",
        type=int,
        default=50,
        help="Maximum modified files allowed in a PR diff before skipping review",
    )
    return parser.parse_args(args)


def get_pr_diff(pr_number: Optional[int]) -> str:
    """Fetch PR diff via gh CLI."""
    cmd = ["gh", "pr", "diff"]
    if pr_number:
        cmd.append(str(pr_number))
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return res.stdout
    except Exception as err:
        raise RuntimeError(f"Could not fetch diff via `gh pr diff`: {err}") from err


def get_pr_metadata(pr_number: Optional[int]) -> Dict[str, str]:
    """Fetch PR title and description via gh CLI."""
    cmd = ["gh", "pr", "view", "--json", "title,body,number,headRefName,baseRefName"]
    if pr_number:
        cmd.append(str(pr_number))
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(res.stdout)
    except Exception as err:
        raise RuntimeError(f"Could not fetch PR metadata via `gh pr view`: {err}") from err


def get_repo_instructions() -> str:
    """Discover and read repository-specific instruction files if present."""
    candidate_paths = [
        "AGENTS.md",
        "CLAUDE.md",
        "GEMINI.md",
        ".github/copilot-instructions.md",
        ".github/ANTIGRAVITY.md",
    ]
    instructions = []
    workspace_root = os.environ.get("GITHUB_WORKSPACE", ".")
    for rel_path in candidate_paths:
        full_path = os.path.join(workspace_root, rel_path)
        if os.path.isfile(full_path):
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        instructions.append(f"--- From `{rel_path}` ---\n{content}")
            except Exception as err:
                print(f"::warning::Could not read repo instruction file {full_path}: {err}", file=sys.stderr)
    return "\n\n".join(instructions)


def build_full_prompt(mode: str, pr_meta: Dict[str, str], diff: str, addendum: str) -> str:
    """Construct the complete prompt for the Antigravity Agent."""
    base_instructions = MODE_PROMPTS.get(mode, MODE_PROMPTS["code-review"])
    
    pr_title = pr_meta.get("title", "N/A")
    pr_body = pr_meta.get("body", "N/A")
    pr_num = pr_meta.get("number", "N/A")

    prompt_parts = [
        f"Task Mode: {mode.upper()}",
        f"Pull Request: #{pr_num} - {pr_title}",
        f"Description:\n{pr_body}\n",
        "Instructions:",
        base_instructions,
    ]

    repo_guidelines = get_repo_instructions()
    if repo_guidelines:
        prompt_parts.append(f"\nRepository Guidelines & Standards:\n{repo_guidelines}")

    if addendum and addendum.strip():
        prompt_parts.append(f"\nAdditional Caller Guidance:\n{addendum.strip()}")

    if diff:
        prompt_parts.append(f"\nPull Request Diff:\n```diff\n{diff}\n```")
    else:
        prompt_parts.append("\nNote: Pull Request diff was empty or unresolvable.")

    return "\n\n".join(prompt_parts)


def normalize_diff_path(raw_path: str) -> str:
    """Clean and normalize a file path from diffs or location tags."""
    if not raw_path:
        return ""
    cleaned = str(raw_path).strip("'\"` ").replace("\\", "/")
    if cleaned.startswith('"') and cleaned.endswith('"'):
        cleaned = cleaned[1:-1].strip()
    normalized = os.path.normpath(cleaned).replace("\\", "/").lstrip("/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    if normalized.startswith("a/") or normalized.startswith("b/"):
        normalized = normalized[2:]
    return normalized


def parse_json_inline_comments(content: str) -> List[Dict[str, Any]]:
    """Attempt to parse structured JSON inline finding block from report content.

    Looks for a fenced ```json block containing a list of finding objects:
    ```json
    [
      {
        "path": "file.py",
        "start_line": 10,
        "end_line": 15,
        "title": "Finding Title",
        "body": "Detailed description"
      }
    ]
    ```
    """
    json_block_pat = re.compile(r"```json\s*(\[\s*\{.*\}\s*\])\s*```", re.DOTALL | re.IGNORECASE)
    match = json_block_pat.search(content)
    if not match:
        json_list_pat = re.compile(r"(\[\s*\{\s*\"path\".*\}\s*\])", re.DOTALL)
        match = json_list_pat.search(content)
        if not match:
            return []

    json_str = match.group(1).strip()
    try:
        items = json.loads(json_str)
        if not isinstance(items, list):
            return []
    except Exception:
        return []

    comments = []
    for item in items:
        if not isinstance(item, dict):
            continue
        file_path = normalize_diff_path(str(item.get("path", "")))
        if not file_path:
            continue

        start_line = item.get("start_line") or item.get("line")
        if start_line is None:
            continue
        try:
            start_line = max(1, int(start_line))
        except (ValueError, TypeError):
            continue

        end_line = item.get("end_line")
        if end_line is not None:
            try:
                end_line = max(1, int(end_line))
            except (ValueError, TypeError):
                end_line = None

        title = str(item.get("title", "")).strip()
        body = str(item.get("body", "")).strip()
        if not body and not title:
            continue

        if title:
            comment_body = f"#### {title}\n\n{body}".strip() if body else f"#### {title}"
        else:
            comment_body = body

        comment_obj = {
            "path": file_path,
            "side": "RIGHT",
            "body": comment_body,
        }
        if end_line and end_line != start_line:
            comment_obj["start_line"] = min(start_line, end_line)
            comment_obj["line"] = max(start_line, end_line)
            comment_obj["start_side"] = "RIGHT"
        else:
            comment_obj["line"] = start_line

        comments.append(comment_obj)

    return comments


def extract_inline_comments(content: str) -> List[Dict[str, Any]]:
    """Parse line-anchored finding locations from agent report markdown.

    First attempts parsing structured JSON inline findings block.
    If no valid JSON findings block is present, falls back to regex matching.
    """
    json_comments = parse_json_inline_comments(content)
    if json_comments:
        return json_comments

    loc_pat = re.compile(
        r'(?:\*\*|\*|_)?Location(?:\*\*|\*|_)?:\*?\*?[ \t\n]*\[(?P<file>[^:\]]+):L?(?P<start>\d+)(?:-L?(?P<end>\d+))?\]',
        re.IGNORECASE,
    )
    # Mask fenced code blocks with whitespace to prevent matching location tags inside code blocks.
    # Line-anchor opening/closing fences (supporting up to 3 leading spaces & matching backtick counts)
    # so unclosed backticks don't span across findings.
    fence_pat = re.compile(r"^[ \t]{0,3}(`{3,})[^\n]*\n.*?\n[ \t]{0,3}\1[ \t]*$", re.MULTILINE | re.DOTALL)
    content_masked = fence_pat.sub(lambda m: " " * len(m.group(0)), content)
    matches = list(loc_pat.finditer(content_masked))
    if not matches:
        return []

    # Pre-calculate section header start position for each location match (if a header exists between previous match and current match)
    parsed_items = []
    for i, match in enumerate(matches):
        prev_end = matches[i - 1].end() if i > 0 else 0
        preceding_text = content_masked[prev_end:match.start()]
        headers = list(re.finditer(r"^[ \t]*\#{2,6}[ \t]+[^\n]+", preceding_text, re.MULTILINE))
        if headers:
            last_header = headers[-1]
            header_text = last_header.group(0).strip()
            header_start = prev_end + last_header.start()
            header_end = prev_end + last_header.end()
            pre_location_text = preceding_text[last_header.end():].strip()
        else:
            header_text = ""
            header_start = match.start()
            header_end = match.start()
            pre_location_text = ""
        parsed_items.append({
            "match": match,
            "header_text": header_text,
            "header_start": header_start,
            "header_end": header_end,
            "pre_location_text": pre_location_text,
        })

    comments = []
    for i, item in enumerate(parsed_items):
        match = item["match"]
        header_text = item["header_text"]
        pre_location_text = item["pre_location_text"]
        file_path = normalize_diff_path(match.group("file"))
        if not file_path:
            continue
        start_line = max(1, int(match.group("start")))
        end_line = max(1, int(match.group("end"))) if match.group("end") else None

        body_start = match.end()
        body_end = parsed_items[i + 1]["header_start"] if i + 1 < len(parsed_items) else len(content)
        raw_body = content[body_start:body_end].strip()

        # Mask code blocks with spaces to preserve identical character offsets
        # across all matches and avoid false summary-header hits on code comments.
        body_masked = fence_pat.sub(lambda m: " " * len(m.group(0)), raw_body)
        # Use (?:^|\n+) so summary headers at start of raw_body or after newlines are caught.
        # Restrict keywords to top-level report summary headings — bare
        # "Recommendation" or "Summary of X" inside a finding is excluded.
        summary_match = re.search(
            r"(?:^|\n+)\#{1,6}[ \t]+(?:Summary|Conclusion|Overall[ \t]+(?:Summary|Recommendations?)|General[ \t]+(?:Summary|Recommendations?))\b(?![ \t]+(?:of|for|regarding|table|details))\b",
            body_masked,
            re.IGNORECASE,
        )
        if summary_match:
            raw_body = raw_body[:summary_match.start()].strip()

        body_parts = []
        if header_text:
            body_parts.append(header_text)
        if pre_location_text:
            body_parts.append(pre_location_text)
        if raw_body:
            body_parts.append(raw_body)

        if not body_parts or (not raw_body and not pre_location_text):
            continue

        body_text = "\n\n".join(body_parts).strip()

        comment_obj = {
            "path": file_path,
            "side": "RIGHT",
            "body": body_text,
        }

        if end_line and end_line != start_line:
            comment_obj["start_line"] = min(start_line, end_line)
            comment_obj["line"] = max(start_line, end_line)
            comment_obj["start_side"] = "RIGHT"
        else:
            comment_obj["line"] = start_line

        comments.append(comment_obj)
    return comments


def parse_diff_valid_lines(diff_text: str) -> Dict[str, Set[int]]:
    """Parse unified git diff output into a mapping of file_path -> set of valid line numbers on the target branch (RIGHT side)."""
    valid_lines: Dict[str, Set[int]] = {}
    if not diff_text:
        return valid_lines

    current_file: Optional[str] = None
    hunk_header_pat = re.compile(r"^@@\s+-\d+(?:,\d+)?\s+\+(?P<start>\d+)(?:,(?P<count>\d+))?\s+@@")

    for line in diff_text.split("\n"):
        line_str = line.rstrip("\r")
        if line_str.startswith("diff --git "):
            current_file = None
            continue
        elif line_str.startswith("+++ b/") or line_str.startswith('+++ "b/'):
            raw_path = line_str[4:].strip()
            current_file = normalize_diff_path(raw_path)
            if current_file and current_file not in valid_lines:
                valid_lines[current_file] = set()
            continue
        elif line_str.startswith("+++ /dev/null"):
            current_file = None
            continue
        elif line_str.startswith("--- "):
            continue

        if current_file is not None:
            match = hunk_header_pat.match(line_str)
            if match:
                start = int(match.group("start"))
                count_str = match.group("count")
                count = int(count_str) if count_str is not None else 1
                for line_num in range(start, start + count):
                    valid_lines[current_file].add(line_num)

    return valid_lines


def validate_inline_comments(
    inline_comments: List[Dict[str, Any]], valid_lines: Dict[str, Set[int]]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Filter proposed inline comments against valid diff hunk lines.

    Returns a tuple of (valid_comments, invalid_comments).
    An inline comment is valid if its file exists in valid_lines and all line numbers
    it targets are present in active diff hunks.
    """
    if not valid_lines:
        return [], list(inline_comments)

    valid_comments = []
    invalid_comments = []

    for comment in inline_comments:
        path = comment.get("path", "")
        if path not in valid_lines:
            invalid_comments.append(comment)
            continue

        file_lines = valid_lines[path]
        line = comment.get("line")
        start_line = comment.get("start_line", line)

        if line is None:
            invalid_comments.append(comment)
            continue

        target_start = start_line if start_line is not None else line
        target_range = range(target_start, line + 1)
        if all(l in file_lines for l in target_range):
            valid_comments.append(comment)
        else:
            invalid_comments.append(comment)

    return valid_comments, invalid_comments


def post_github_comment(pr_number: Optional[int], content: str, mode: str, diff: str = ""):
    """Post agent analysis report as a GitHub PR review (with inline comments if present) or issue comment."""
    header = f"### 🤖 Antigravity Agent Report ({mode.title()})\n\n"
    # Strip trailing JSON findings block from main PR report body so output remains clean for human readers
    clean_content = re.sub(r"\n*```json\s*\[\s*\{.*\}\s*\]\s*```\s*$", "", content, flags=re.DOTALL | re.IGNORECASE).strip()
    full_body = header + clean_content

    json_comments = parse_json_inline_comments(content)
    is_json_report = bool(json_comments)
    inline_comments = extract_inline_comments(content)
    resolved_pr_num = None

    if inline_comments:
        if not diff and (pr_number or os.environ.get("GITHUB_REF")):
            try:
                diff = get_pr_diff(pr_number)
            except Exception:
                diff = ""

        valid_lines = parse_diff_valid_lines(diff) if diff else {}
        valid_comments, invalid_comments = validate_inline_comments(inline_comments, valid_lines)

        # Only append off-diff findings to full_body for JSON block reports (where the JSON block was stripped from clean_content).
        # For markdown-extracted findings (Location: [file:L10]), the findings text is already present in clean_content / full_body.
        if invalid_comments and is_json_report:
            off_diff_lines = ["\n\n### 📌 Additional Findings (Off-diff)"]
            for c in invalid_comments:
                c_path = c.get("path", "")
                c_line = c.get("line", "")
                c_body = c.get("body", "")
                off_diff_lines.append(f"**Location:** `{c_path}:L{c_line}`\n{c_body}")
            full_body += "\n\n" + "\n\n".join(off_diff_lines)

        if valid_comments:
            try:
                cmd_pr = ["gh", "pr", "view"]
                if pr_number:
                    cmd_pr.append(str(pr_number))
                cmd_pr.extend(["--json", "number,headRefOid"])
                res_pr = subprocess.run(cmd_pr, capture_output=True, text=True, check=True)
                pr_data = json.loads(res_pr.stdout)
                resolved_pr_num = pr_data.get("number")
                head_sha = pr_data.get("headRefOid")

                if head_sha and resolved_pr_num:
                    payload = {
                        "commit_id": head_sha,
                        "body": full_body,
                        "event": "COMMENT",
                        "comments": valid_comments,
                    }
                    repo_slug = os.environ.get("GITHUB_REPOSITORY")
                    if not repo_slug:
                        try:
                            res_repo = subprocess.run(["gh", "repo", "view", "--json", "nameWithOwner"], capture_output=True, text=True, check=True)
                            repo_slug = json.loads(res_repo.stdout).get("nameWithOwner")
                        except Exception:
                            repo_slug = None

                    if not repo_slug or repo_slug == "{owner}/{repo}":
                        raise ValueError("Could not resolve GITHUB_REPOSITORY for inline review submission.")
                    api_cmd = [
                        "gh", "api",
                        f"repos/{repo_slug}/pulls/{resolved_pr_num}/reviews",
                        "--input", "-"
                    ]
                    res_review = subprocess.run(
                        api_cmd,
                        input=json.dumps(payload),
                        capture_output=True,
                        text=True,
                    )
                    if res_review.returncode == 0:
                        print(f"Successfully posted Antigravity agent review with {len(valid_comments)} inline comment(s) to PR #{resolved_pr_num}.")
                        return
                    else:
                        print(f"::warning::Failed to post inline PR review ({res_review.stderr.strip()}); falling back to PR comment.", file=sys.stderr)
            except Exception as err:
                print(f"::warning::Could not post inline review ({err}); falling back to PR comment.", file=sys.stderr)

    cmd = ["gh", "pr", "comment"]
    target_pr = resolved_pr_num or pr_number
    if target_pr:
        cmd.append(str(target_pr))
    cmd.extend(["--body", full_body])

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Failed to post GitHub comment via gh CLI: {res.stderr}")
    print(f"Successfully posted Antigravity agent report to PR #{target_pr or 'current'}.")


async def run_antigravity_agent(prompt: str, system_instruction: str, model: str = "") -> str:
    """Async execution of the Google Antigravity Agent SDK."""
    if Agent is None:
        raise RuntimeError(
            "google-antigravity SDK is not installed. Install via `pip install google-antigravity`."
        )

    # Restrict capabilities to read-only tools for security against prompt injection
    capabilities = (
        CapabilitiesConfig(
            enabled_tools=[
                BuiltinTools.VIEW_FILE,
                BuiltinTools.LIST_DIR,
                BuiltinTools.SEARCH_DIR,
                BuiltinTools.FIND_FILE,
            ]
        )
        if BuiltinTools is not None
        else CapabilitiesConfig()
    )

    config_kwargs = {
        "system_instructions": system_instruction,
        "capabilities": capabilities,
    }
    if model and model.strip():
        config_kwargs["model"] = model.strip()

    config = LocalAgentConfig(**config_kwargs)

    max_retries = 3
    base_delay = 5
    for attempt in range(1, max_retries + 1):
        try:
            chunks = []
            async with Agent(config) as agent:
                response = await agent.chat(prompt)
                async for token in response:
                    chunks.append(token)

            output = "".join(chunks)
            sys.stdout.write(output)
            sys.stdout.flush()
            print()
            return output
        except Exception as err:
            err_str = str(err)
            err_upper = err_str.upper()
            status_code = getattr(err, "status_code", None)
            if status_code is None and hasattr(err, "code"):
                code_attr = getattr(err, "code")
                status_code = code_attr() if callable(code_attr) else code_attr
            is_transient = (
                status_code in (429, 500, 502, 503, 504)
                or str(status_code) in ("429", "500", "502", "503", "504")
                or "429" in err_str
                or any(
                    kw in err_upper
                    for kw in (
                        "QUOTA",
                        "RATE_LIMIT",
                        "RESOURCE_EXHAUSTED",
                        "TOO_MANY_REQUESTS",
                        "THROTTLED",
                        "UNAVAILABLE",
                        "OVERLOADED",
                    )
                )
            )
            if is_transient and attempt < max_retries:
                delay = (base_delay * (2 ** (attempt - 1))) + random.uniform(0, 1)
                print(
                    f"::warning::Antigravity Agent encountered API rate limit or transient error ({status_code or 'transient'}). Retrying in {delay:.2f}s (attempt {attempt}/{max_retries})...",
                    file=sys.stderr,
                )
                await asyncio.sleep(delay)
            else:
                raise


def main():
    args = parse_args()
    
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    if args.trigger_policy == "on-push" and event_name and event_name not in ("pull_request", "pull_request_target"):
        print(f"Trigger policy 'on-push' enforced: skipping execution for event '{event_name}'.")
        return
    if args.trigger_policy == "on-request" and event_name and event_name != "workflow_dispatch":
        print(f"Trigger policy 'on-request' enforced: skipping execution for event '{event_name}'.")
        return

    try:
        pr_meta = get_pr_metadata(args.pr_number)
    except Exception as err:
        if args.dry_run:
            print(f"Warning: Could not fetch PR metadata in dry-run mode: {err}", file=sys.stderr)
            pr_meta = {}
        else:
            print(f"::error::Failed to fetch PR metadata: {err}", file=sys.stderr)
            sys.exit(1 if args.fail_on_error else 0)

    pr_num = args.pr_number or pr_meta.get("number")


    try:
        diff = get_pr_diff(pr_num)
    except Exception as err:
        if args.dry_run:
            print(f"Warning: Could not fetch PR diff in dry-run mode: {err}", file=sys.stderr)
            diff = ""
        else:
            print(f"::error::Failed to fetch PR diff: {err}", file=sys.stderr)
            sys.exit(1 if args.fail_on_error else 0)

    if diff:
        # Check diff size limits
        lines = diff.splitlines()
        # Header lines carry a trailing SPACE ("+++ b/path"), so match that
        # rather than the bare marker: a genuine added line whose content
        # begins "++" (C++ increments, nested Markdown markers) becomes
        # "+++..." once the diff prefix is added, and a bare-marker test
        # silently drops it from the count (gha#672 review, finding 6).
        changed_lines = sum(
            1
            for line in lines
            if (line.startswith("+") and not line.startswith("+++ "))
            or (line.startswith("-") and not line.startswith("--- "))
        )
        files_changed = sum(1 for line in lines if line.startswith("diff --git"))
        
        def _skip_notice(what: str, actual: int, limit: int) -> None:
            """Announce a size skip on the THREAD, not just in the job log.

            A size skip is not a failure, so it exits 0 regardless of
            --fail-on-error -- which means a green check is all the PR shows.
            Logging to stderr and exiting leaves the thread indistinguishable
            from "the reviewer has not run yet", the same silent-thread class
            the error paths above were fixed for, and the one
            report-gemini-failure (gha#379) posts a comment for even on a
            graceful skip. gha#672 review, round 3.
            """
            msg = (
                f"::warning::PR diff exceeds {what} ({actual} > {limit}). "
                "Skipping review."
            )
            print(msg, file=sys.stderr)
            if args.post_comment:
                body = (
                    f"> [!WARNING]\n"
                    f"> **Antigravity review skipped: diff too large.**\n"
                    f"> This PR's diff has {actual} {what.replace('max-diff-', '')}, "
                    f"over the `{what}` limit of {limit}.\n"
                    f">\n"
                    f"> The check is green because a size skip is not a failure, "
                    f"but **no review was performed**. Raise `{what}` on the "
                    f"caller, or split the PR."
                )
                try:
                    post_github_comment(pr_num, body, args.mode, diff=diff)
                except Exception as err:  # never let the notice fail the run
                    print(f"::warning::Could not post the size-skip notice: {err}", file=sys.stderr)

        if changed_lines > args.max_diff_lines:
            _skip_notice("max-diff-lines", changed_lines, args.max_diff_lines)
            sys.exit(0)
        
        if files_changed > args.max_diff_files:
            _skip_notice("max-diff-files", files_changed, args.max_diff_files)
            sys.exit(0)

    system_instruction = (
        f"You are the Google Antigravity AI Agent running in automated mode ({args.mode}). "
        "Provide thorough, high-quality, professional software engineering analysis."
    )
    
    full_prompt = build_full_prompt(args.mode, pr_meta, diff, args.prompt_addendum)

    if args.dry_run:
        print("=== DRY RUN MODE ===")
        print(f"Model: {args.model}")
        print(f"Trigger Policy: {args.trigger_policy}")
        print(f"System Instructions: {system_instruction}")
        print("--- Full Prompt ---")
        print(full_prompt)
        return

    if not diff:
        print("::error::Empty diff fetched for analysis.", file=sys.stderr)
        sys.exit(1 if args.fail_on_error else 0)

    try:
        report = asyncio.run(run_antigravity_agent(full_prompt, system_instruction, model=args.model))
        if args.post_comment and report:
            post_github_comment(pr_num, report, args.mode, diff=diff)
    except Exception as err:
        print(f"Execution failed: {err}", file=sys.stderr)
        sys.exit(1 if args.fail_on_error else 0)


if __name__ == "__main__":
    main()
