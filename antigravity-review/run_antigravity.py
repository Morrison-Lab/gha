#!/usr/bin/env python3
"""Run automated agentic code reviews, security audits, or test-suite generation

using the Google Antigravity Python SDK (google-antigravity).
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from typing import Dict, Optional

try:
    from google.antigravity import Agent, LocalAgentConfig, CapabilitiesConfig
except ImportError:
    # Fallback / mock support for offline unit testing without SDK installed
    Agent = None
    LocalAgentConfig = None
    CapabilitiesConfig = None


MODE_PROMPTS = {
    "code-review": (
        "You are an expert AI code reviewer. Review the provided pull request diff. "
        "Report architectural concerns, bugs, edge cases, performance issues, readability improvements, "
        "and missing test coverage. Provide actionable, constructive feedback with clear code examples where applicable."
    ),
    "security-audit": (
        "You are a principal security engineer conducting a security audit on the pull request diff. "
        "Check for OWASP Top 10 vulnerabilities, credential or key leakage, improper input validation, "
        "injection risks, authentication/authorization gaps, and sensitive data (PHI/PII) exposure. "
        "Classify findings by severity (Critical, High, Medium, Low) and provide defensive remediation guidance."
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
        default="gemini-2.5-flash",
        help="Model override (e.g. gemini-2.5-flash, gemini-2.5-pro)",
    )
    parser.add_argument(
        "--prompt-addendum",
        default="",
        help="Additional instructions to append to the agent prompt",
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
    except (subprocess.CalledProcessError, FileNotFoundError) as err:
        print(f"Warning: Could not fetch diff via `gh pr diff`: {err}", file=sys.stderr)
        return ""


def get_pr_metadata(pr_number: Optional[int]) -> Dict[str, str]:
    """Fetch PR title and description via gh CLI."""
    cmd = ["gh", "pr", "view", "--json", "title,body,number,headRefName,baseRefName"]
    if pr_number:
        cmd.append(str(pr_number))
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(res.stdout)
    except Exception as err:
        print(f"Warning: Could not fetch PR metadata via `gh pr view`: {err}", file=sys.stderr)
        return {}


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

    if addendum and addendum.strip():
        prompt_parts.append(f"\nAdditional Caller Guidance:\n{addendum.strip()}")

    if diff:
        prompt_parts.append(f"\nPull Request Diff:\n```diff\n{diff}\n```")
    else:
        prompt_parts.append("\nNote: Pull Request diff was empty or unresolvable.")

    return "\n\n".join(prompt_parts)


def post_github_comment(pr_number: Optional[int], content: str, mode: str):
    """Post agent analysis report as a PR comment using gh CLI."""
    header = f"### 🤖 Antigravity Agent Report ({mode.title()})\n\n"
    full_body = header + content
    cmd = ["gh", "pr", "comment"]
    if pr_number:
        cmd.append(str(pr_number))
    cmd.extend(["--body", full_body])

    try:
        subprocess.run(cmd, check=True)
        print(f"Successfully posted Antigravity agent report to PR #{pr_number or 'current'}.")
    except Exception as err:
        print(f"Error posting GitHub comment: {err}", file=sys.stderr)


async def run_antigravity_agent(prompt: str, system_instruction: str) -> str:
    """Async execution of the Google Antigravity Agent SDK."""
    if Agent is None:
        raise RuntimeError(
            "google-antigravity SDK is not installed. Install via `pip install google-antigravity`."
        )

    config = LocalAgentConfig(
        system_instructions=system_instruction,
        capabilities=CapabilitiesConfig(),
    )

    chunks = []
    async with Agent(config) as agent:
        response = await agent.chat(prompt)
        async for token in response:
            chunks.append(token)
            sys.stdout.write(token)
            sys.stdout.flush()
    print()
    return "".join(chunks)


def main():
    args = parse_args()
    
    pr_meta = get_pr_metadata(args.pr_number)
    pr_num = args.pr_number or pr_meta.get("number")
    diff = get_pr_diff(pr_num)

    system_instruction = (
        f"You are the Google Antigravity AI Agent running in automated mode ({args.mode}). "
        "Provide thorough, high-quality, professional software engineering analysis."
    )
    
    full_prompt = build_full_prompt(args.mode, pr_meta, diff, args.prompt_addendum)

    if args.dry_run:
        print("=== DRY RUN MODE ===")
        print(f"System Instructions: {system_instruction}")
        print("--- Full Prompt ---")
        print(full_prompt)
        return

    try:
        report = asyncio.run(run_antigravity_agent(full_prompt, system_instruction))
        if args.post_comment and report:
            post_github_comment(pr_num, report, args.mode)
    except Exception as err:
        print(f"Execution failed: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
