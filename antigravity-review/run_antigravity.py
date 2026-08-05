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
from typing import Any, Dict, List, Optional

try:
    from google.antigravity import Agent, LocalAgentConfig, CapabilitiesConfig, BuiltinTools
except ImportError:
    # Fallback / mock support for offline unit testing without SDK installed
    Agent = None
    LocalAgentConfig = None
    CapabilitiesConfig = None
    BuiltinTools = None


LOCATION_GUIDANCE = (
    "\n\nFor file-specific findings, include a location header formatted as:\n"
    "**Location:** [relative/path/to/file.ext:L12] (or [path/to/file.ext:L12-L20] for line ranges).\n"
    "This allows your findings to be posted as line-anchored inline PR review comments."
)

MODE_PROMPTS = {
    "code-review": (
        "You are an expert AI code reviewer. Review the provided pull request diff. "
        "Report architectural concerns, bugs, edge cases, performance issues, readability improvements, "
        "and missing test coverage. Provide actionable, constructive feedback with clear code examples where applicable."
        + LOCATION_GUIDANCE
    ),
    "security-audit": (
        "You are a principal security engineer conducting a security audit on the pull request diff. "
        "Check for OWASP Top 10 vulnerabilities, credential or key leakage, improper input validation, "
        "injection risks, authentication/authorization gaps, and sensitive data (PHI/PII) exposure. "
        "Classify findings by severity (Critical, High, Medium, Low) and provide defensive remediation guidance."
        + LOCATION_GUIDANCE
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
        ".github/copilot-instructions.md",
        ".github/ANTIGRAVITY.md",
    ]
    instructions = []
    for rel_path in candidate_paths:
        if os.path.isfile(rel_path):
            try:
                with open(rel_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        instructions.append(f"--- From `{rel_path}` ---\n{content}")
            except Exception as err:
                print(f"::warning::Could not read repo instruction file {rel_path}: {err}", file=sys.stderr)
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


def extract_inline_comments(content: str) -> List[Dict[str, Any]]:
    """Parse line-anchored finding locations from agent report markdown.

    Matches patterns like `Location: [file.py:L12]` or `**Location:** [path/to/file.py:12-20]`.
    Ignores false location headers inside fenced code blocks.
    """
    header_loc_pat = re.compile(
        r'(?:(?P<header>\#{1,6}[ \t]+[^\n]+\n+)[ \t\n]*)?(?:\*\*|\*|_)?Location(?:\*\*|\*|_)?:\*?\*?[ \t\n]*\[(?P<file>[^:\]]+):L?(?P<start>\d+)(?:-L?(?P<end>\d+))?\]',
        re.IGNORECASE,
    )
    # Mask fenced code blocks with whitespace to prevent matching location tags inside code blocks
    content_masked = re.sub(r"```.*?```", lambda m: " " * len(m.group(0)), content, flags=re.DOTALL)
    matches = list(header_loc_pat.finditer(content_masked))
    comments = []
    for i, match in enumerate(matches):
        file_path = match.group("file").strip("'\" ")
        if file_path.startswith("./"):
            file_path = file_path[2:]
        start_line = max(1, int(match.group("start")))
        end_line = max(1, int(match.group("end"))) if match.group("end") else None
        header_text = match.group("header").strip() if match.group("header") else ""

        body_start = match.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        raw_body = content[body_start:body_end].strip()

        if i + 1 == len(matches):
            # Mask code blocks with spaces to preserve identical character offsets
            body_masked = re.sub(r"```.*?```", lambda m: " " * len(m.group(0)), raw_body, flags=re.DOTALL)
            summary_match = re.search(r"\n{2,}\#{1,6}[ \t]+(?:Summary|Conclusion|Recommendation|General|Overall)", body_masked, re.IGNORECASE)
            if summary_match:
                raw_body = raw_body[:summary_match.start()].strip()

        body_text = f"{header_text}\n\n{raw_body}".strip() if header_text else raw_body

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


def post_github_comment(pr_number: Optional[int], content: str, mode: str):
    """Post agent analysis report as a GitHub PR review (with inline comments if present) or issue comment."""
    header = f"### 🤖 Antigravity Agent Report ({mode.title()})\n\n"
    full_body = header + content

    inline_comments = extract_inline_comments(content)
    resolved_pr_num = None

    if inline_comments:
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
                    "comments": inline_comments,
                }
                repo_slug = os.environ.get("GITHUB_REPOSITORY")
                if not repo_slug:
                    try:
                        res_repo = subprocess.run(["gh", "repo", "view", "--json", "nameWithOwner"], capture_output=True, text=True, check=True)
                        repo_slug = json.loads(res_repo.stdout).get("nameWithOwner")
                    except Exception:
                        repo_slug = "{owner}/{repo}"
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
                    print(f"Successfully posted Antigravity agent review with {len(inline_comments)} inline comment(s) to PR #{resolved_pr_num}.")
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
            sys.exit(1)

    pr_num = args.pr_number or pr_meta.get("number")

    try:
        diff = get_pr_diff(pr_num)
    except Exception as err:
        if args.dry_run:
            print(f"Warning: Could not fetch PR diff in dry-run mode: {err}", file=sys.stderr)
            diff = ""
        else:
            print(f"::error::Failed to fetch PR diff: {err}", file=sys.stderr)
            sys.exit(1)

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
        sys.exit(1)

    try:
        report = asyncio.run(run_antigravity_agent(full_prompt, system_instruction, model=args.model))
        if args.post_comment and report:
            post_github_comment(pr_num, report, args.mode)
    except Exception as err:
        print(f"Execution failed: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
