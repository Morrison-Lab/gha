#!/usr/bin/env python3
"""Write a student-copy check's condor-batch steps: both profiles, each question, the check.

Inputs come from the student-copy-render composite's SC_* environment. The first question
renders alone so the pre-render scripts finish first; the rest share no output, so run in parallel.
"""

import os

from fail import fail
from fragment_line import fragment_line
from list_path import list_path


def build(env: dict[str, str]) -> list[str]:
    check = env.get("SC_CHECK", "").strip()
    if not check:
        fail("check is required")
    if "\n" in check:
        fail("check must be one line; condor-batch runs each line in its own shell")
    parallel_text = env.get("SC_PARALLEL", "4").strip() or "4"
    if not parallel_text.isdigit() or int(parallel_text) < 1:
        fail(f"parallel must be a whole number of at least 1, not {parallel_text!r}")
    documents = env.get("SC_DOCUMENTS", "all").strip() or "all"
    if documents == "all":
        renders = ["quarto render", "quarto render --profile solution"]
    else:
        path = list_path("documents", documents)
        renders = [f"xargs -r -a {path} -I{{}} quarto render {{}}{p}" for p in ("", " --profile solution")]
    fragments = env.get("SC_FRAGMENTS", "all").strip() or "all"
    glob = env.get("SC_FRAGMENT_GLOB", "exercises/*/_exr-*.qmd").strip()
    return [*renders, fragment_line(fragments, glob, int(parallel_text)), check]


if __name__ == "__main__":
    print("\n".join(build(dict(os.environ))))
