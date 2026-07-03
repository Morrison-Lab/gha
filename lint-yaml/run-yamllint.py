#!/usr/bin/env python3
"""
Run yamllint over the caller repo's tracked YAML files.

Configuration (all via environment variables, set by the composite action):
  YAMLLINT_CONFIG_FILE  Path (in the caller repo) to a yamllint config file.
                         Falls back to the bundled .yamllint.default.yml when
                         empty or the file does not exist.
  YAMLLINT_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  YAMLLINT_FAIL          "true" (default) => exit 1 when yamllint reports an
                          error; otherwise warn (yamllint's own report is
                          still printed) but exit 0.
"""

import os
import subprocess
import sys
from pathlib import Path

from _pathspec import compile_ignores, split_list, tracked_files


def resolve_config(action_path: Path) -> Path:
    override = os.environ.get("YAMLLINT_CONFIG_FILE", "").strip()
    if override and os.path.isfile(override):
        print(f"Using caller-provided yamllint config: {override}")
        return Path(override)
    default = action_path / ".yamllint.default.yml"
    print("Using bundled default yamllint config")
    return default


def main() -> int:
    action_path = Path(os.environ["GITHUB_ACTION_PATH"])
    ignores = compile_ignores(split_list(os.environ.get("YAMLLINT_PATHS_IGNORE", "")))
    fail = os.environ.get("YAMLLINT_FAIL", "true").strip().lower() != "false"

    files = tracked_files(["*.yml", "*.yaml"], ignores)
    if not files:
        print("No tracked .yml/.yaml files to lint.")
        return 0

    config = resolve_config(action_path)
    result = subprocess.run(
        [sys.executable, "-m", "yamllint", "-c", str(config), "--", *files]
    )

    if result.returncode != 0 and not fail:
        print("yamllint reported errors above, but fail=false; continuing.")
        return 0
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
