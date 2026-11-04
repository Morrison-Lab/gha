"""Self-tests for lint_qmd_chunks.py; run with `python3 -m unittest`."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "lint_qmd_chunks.py"
CONFIG = HERE / "ruff.toml"

CLEAN = """# Title

```{python}
#| echo: true
import math

x = math.pi
x
```

Prose.

```{python}
y = x + 1;
```
"""

BAD = """# Title

```{python}
z = 1
if z == None:
    pass
```

```{python}
f = lambda: 1
```
"""

R_ONLY = """# Title

```{r}
x <- 1
```
"""


def lint(text):
    with tempfile.TemporaryDirectory() as scratch:
        path = Path(scratch) / "page.qmd"
        path.write_text(text, encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--config", str(CONFIG), str(path)],
            capture_output=True,
            text=True,
            check=False,
        )


INDENTED = """::: {.callout-note}
  ```{python}
  x = 1
  if x == None:
      pass
  ```
:::
"""


class LintQmdChunks(unittest.TestCase):
    def test_indented_chunks_are_dedented(self):
        result = lint(INDENTED)
        self.assertEqual(result.returncode, 1)
        self.assertIn("page.qmd:4: E711", result.stdout)
        self.assertNotIn("invalid-syntax", result.stdout)

    def test_clean_file_passes(self):
        result = lint(CLEAN)
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_findings_are_reported_at_qmd_lines(self):
        result = lint(BAD)
        self.assertEqual(result.returncode, 1)
        self.assertIn("page.qmd:5: E711", result.stdout)
        self.assertIn("page.qmd:10: E731", result.stdout)

    def test_longer_closing_fence_closes_the_chunk(self):
        text = BAD.replace("pass\n```\n", "pass\n````\n", 1)
        result = lint(text)
        self.assertIn("page.qmd:5: E711", result.stdout)
        self.assertIn("page.qmd:10: E731", result.stdout)
        self.assertNotIn("invalid-syntax", result.stdout)

    def test_missing_ruff_is_reported_plainly(self):
        with tempfile.TemporaryDirectory() as scratch:
            path = Path(scratch) / "page.qmd"
            path.write_text(BAD, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--config", str(CONFIG), str(path)],
                capture_output=True,
                text=True,
                check=False,
                env={"PATH": scratch},
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn("could not run ruff", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_malformed_config_is_a_could_not_run_exit(self):
        with tempfile.TemporaryDirectory() as scratch:
            page = Path(scratch) / "page.qmd"
            page.write_text(BAD, encoding="utf-8")
            config = Path(scratch) / "ruff.toml"
            config.write_text("line-length = [\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--config", str(config), str(page)],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn("ruff check failed", result.stderr)

    def test_non_python_chunks_are_ignored(self):
        self.assertEqual(lint(R_ONLY).returncode, 0)


if __name__ == "__main__":
    unittest.main()
