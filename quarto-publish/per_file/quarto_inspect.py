"""Run `quarto inspect` and show why it failed."""
import json
import subprocess


def quarto_inspect(project, target):
    """Return `quarto inspect TARGET` as a dict, or None (with its stderr) on failure."""
    result = subprocess.run(
        ["quarto", "inspect", target], cwd=project,
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        print(f"::warning::quarto inspect {target} failed "
              f"(exit {result.returncode}); falling back to the project files.\n"
              f"{result.stderr.strip()}", flush=True)
        return None
    return json.loads(result.stdout)
