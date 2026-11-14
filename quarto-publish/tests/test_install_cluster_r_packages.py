"""install-cluster-r-packages.R reads the caller's `r-packages` input (gha#2007).

The input is documented as space-, comma- or newline-separated, and the
runner-side install splits it on `[[:space:],]+`, so the cluster-side script
must split it the same way. These cases run the real script on packages every
R installation carries, so nothing is installed and no network is needed.
"""

import os
import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "quarto-publish" / "install-cluster-r-packages.R"

# CI sets REQUIRE_RSCRIPT, so a runner that lost R fails instead of skipping.
if shutil.which("Rscript") is None and os.environ.get("REQUIRE_RSCRIPT") == "1":
    raise RuntimeError("REQUIRE_RSCRIPT=1 but Rscript is not on PATH")
pytestmark = pytest.mark.skipif(shutil.which("Rscript") is None, reason="needs Rscript")


def run(tmp_path, specs):
    spec_file = tmp_path / "r-packages.txt"
    spec_file.write_text(specs)
    return subprocess.run(
        ["Rscript", str(SCRIPT), str(tmp_path / "lib"), str(spec_file)],
        capture_output=True, text=True, check=False,
    )


@pytest.mark.parametrize("specs", [
    "any::stats, any::utils\n",
    "any::stats any::utils\n",
    "any::stats\ncran::utils\ntools\n",
    "any::stats,\n  utils ,tools\n# a comment, ignored\n",
])
def test_every_documented_separator_is_split(tmp_path, specs):
    result = run(tmp_path, specs)
    assert result.returncode == 0, result.stderr
    assert "::warning::" not in result.stdout + result.stderr


def test_an_unsupported_form_is_reported_and_skipped(tmp_path):
    result = run(tmp_path, "bioc::Biobase, any::stats\n")
    assert result.returncode == 0, result.stderr
    assert "'bioc::Biobase'" in result.stderr
    assert "any::stats" not in result.stderr
