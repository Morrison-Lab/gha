# check-one-function-per-file: allow-multiple
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# Add parent directory to sys.path to import check_duplicate_roxygen
sys.path.insert(0, str(Path(__file__).parent.parent))
import check_duplicate_roxygen as mod


def test_no_duplicates(tmp_path):
    r_file = tmp_path / "funcs.R"
    r_file.write_text(
        """
#' Compute sum
#' @param a First number to add.
#' @param b Second number to add.
#' @return Sum of a and b.
add <- function(a, b) a + b

#' Compute product
#' @param x First factor.
#' @param y Second factor.
#' @return Product of x and y.
multiply <- function(x, y) x * y
""",
        encoding="utf-8",
    )
    duplicates = mod.find_duplicate_roxygen(tmp_path, {".R"}, [])
    assert len(duplicates) == 0


def test_duplicate_params_same_file(tmp_path):
    r_file = tmp_path / "metrics.R"
    r_file.write_text(
        """
#' Compute mean
#' @param x A numeric vector of observation values to compute metrics over.
#' @return Mean value.
calc_mean <- function(x) mean(x)

#' Compute median
#' @param x A numeric vector of observation values to compute metrics over.
#' @return Median value.
calc_median <- function(x) median(x)
""",
        encoding="utf-8",
    )
    duplicates = mod.find_duplicate_roxygen(tmp_path, {".R"}, [])
    assert len(duplicates) == 1
    group = duplicates[0]
    assert group.param_name == "x"
    assert len(group.occurrences) == 2
    assert any("@inheritParams calc_mean" in r or "@inheritParams calc_median" in r for r in group.recommendations)


def test_duplicate_params_across_files(tmp_path):
    file1 = tmp_path / "fn1.R"
    file1.write_text(
        """
#' Transform data
#' @param data A data frame containing raw participant observations.
#' @export
transform_data <- function(data) data
""",
        encoding="utf-8",
    )

    file2 = tmp_path / "fn2.R"
    file2.write_text(
        """
#' Clean data
#' @param data A data frame containing raw participant observations.
#' @export
clean_data <- function(data) data
""",
        encoding="utf-8",
    )

    duplicates = mod.find_duplicate_roxygen(tmp_path, {".R"}, [])
    assert len(duplicates) == 1
    assert duplicates[0].param_name == "data"
    assert len(duplicates[0].occurrences) == 2


def test_dot_params_recommendation(tmp_path):
    r_file = tmp_path / "wrapper.R"
    r_file.write_text(
        """
#' Core worker
#' @param threshold Significance cutoff value between 0 and 1.
#' @export
core_worker <- function(threshold = 0.05) threshold

#' Public wrapper
#' @param ... Forwarded arguments.
#' @param threshold Significance cutoff value between 0 and 1.
#' @export
public_wrapper <- function(...) core_worker(...)
""",
        encoding="utf-8",
    )
    duplicates = mod.find_duplicate_roxygen(tmp_path, {".R"}, [])
    assert len(duplicates) == 1
    group = duplicates[0]
    assert group.param_name == "threshold"
    # wrapper accepts ... and not threshold, so it should recommend @inheritDotParams
    assert any("@inheritDotParams core_worker threshold" in r for r in group.recommendations)


def test_already_inherits_redundant_param(tmp_path):
    r_file = tmp_path / "redundant.R"
    r_file.write_text(
        """
#' Base function
#' @param config A configuration object containing environment options.
#' @export
base_func <- function(config) config

#' Derived function
#' @inheritParams base_func
#' @param config A configuration object containing environment options.
#' @export
derived_func <- function(config) config
""",
        encoding="utf-8",
    )
    duplicates = mod.find_duplicate_roxygen(tmp_path, {".R"}, [])
    assert len(duplicates) == 1
    group = duplicates[0]
    assert any("already inherited via '@inheritParams base_func'" in r for r in group.recommendations)


def test_multiline_param_description(tmp_path):
    r_file = tmp_path / "multiline.R"
    r_file.write_text(
        """
#' Function A
#' @param obj A complex data structure
#'   containing nested observation
#'   records from laboratory runs.
fn_a <- function(obj) obj

#' Function B
#' @param obj A complex data structure containing nested observation records from laboratory runs.
fn_b <- function(obj) obj
""",
        encoding="utf-8",
    )
    duplicates = mod.find_duplicate_roxygen(tmp_path, {".R"}, [])
    assert len(duplicates) == 1
    assert duplicates[0].param_name == "obj"
    assert (
        duplicates[0].description
        == "A complex data structure containing nested observation records from laboratory runs."
    )


def test_min_desc_length(tmp_path):
    r_file = tmp_path / "short.R"
    r_file.write_text(
        """
#' Func 1
#' @param x Numeric.
f1 <- function(x) x

#' Func 2
#' @param x Numeric.
f2 <- function(x) x
""",
        encoding="utf-8",
    )
    # Default min_desc_length is 10, "Numeric." is 8 chars -> ignored
    duplicates = mod.find_duplicate_roxygen(tmp_path, {".R"}, [], min_desc_length=10)
    assert len(duplicates) == 0

    # With min_desc_length=5 -> detected
    duplicates_low = mod.find_duplicate_roxygen(tmp_path, {".R"}, [], min_desc_length=5)
    assert len(duplicates_low) == 1


def test_file_level_opt_out(tmp_path):
    r_file = tmp_path / "opted_out.R"
    r_file.write_text(
        """# check-duplicate-roxygen: allow-duplicates
#' Func 1
#' @param x A numeric vector of observations.
f1 <- function(x) x

#' Func 2
#' @param x A numeric vector of observations.
f2 <- function(x) x
""",
        encoding="utf-8",
    )
    duplicates = mod.find_duplicate_roxygen(tmp_path, {".R"}, [])
    assert len(duplicates) == 0


def test_block_level_opt_out(tmp_path):
    r_file = tmp_path / "block_opt.R"
    r_file.write_text(
        """
#' Func 1
#' @param x A numeric vector of observations.
f1 <- function(x) x

#' Func 2
#' #' check-duplicate-roxygen: allow-duplicates
#' @param x A numeric vector of observations.
f2 <- function(x) x
""",
        encoding="utf-8",
    )
    duplicates = mod.find_duplicate_roxygen(tmp_path, {".R"}, [])
    assert len(duplicates) == 0


def test_param_level_opt_out(tmp_path):
    r_file = tmp_path / "param_opt.R"
    r_file.write_text(
        """
#' Func 1
#' @param x A numeric vector of observations.
f1 <- function(x) x

#' Func 2
#' @param x A numeric vector of observations. # check-duplicate-roxygen: allow
f2 <- function(x) x
""",
        encoding="utf-8",
    )
    duplicates = mod.find_duplicate_roxygen(tmp_path, {".R"}, [])
    assert len(duplicates) == 0


def test_paths_ignore(tmp_path):
    vendor_dir = tmp_path / "vendor"
    vendor_dir.mkdir()
    vendor_r = vendor_dir / "vendored.R"
    vendor_r.write_text(
        """
#' Vendored 1
#' @param x A numeric vector of observations.
v1 <- function(x) x

#' Vendored 2
#' @param x A numeric vector of observations.
v2 <- function(x) x
""",
        encoding="utf-8",
    )
    duplicates = mod.find_duplicate_roxygen(tmp_path, {".R"}, ["vendor"])
    assert len(duplicates) == 0


def test_extensions_filter(tmp_path):
    txt_file = tmp_path / "doc.txt"
    txt_file.write_text(
        """
#' Not an R file
#' @param x A numeric vector of observations.
f1 <- function(x) x
#' @param x A numeric vector of observations.
f2 <- function(x) x
""",
        encoding="utf-8",
    )
    duplicates = mod.find_duplicate_roxygen(tmp_path, {".R", ".r"}, [])
    assert len(duplicates) == 0


def test_cli_exit_codes(tmp_path):
    r_file = tmp_path / "sample.R"
    r_file.write_text(
        """
#' First
#' @param val An integer value indicating the repetition count.
fn1 <- function(val) val

#' Second
#' @param val An integer value indicating the repetition count.
fn2 <- function(val) val
""",
        encoding="utf-8",
    )

    script = Path(mod.__file__).resolve()

    # With fail=true (default): exit code 1
    res_fail = subprocess.run(
        [sys.executable, str(script), str(tmp_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert res_fail.returncode == 1
    assert "Found 1 duplicate roxygen" in res_fail.stdout

    # With fail=false: exit code 0
    res_pass = subprocess.run(
        [sys.executable, str(script), str(tmp_path), "--fail", "false"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert res_pass.returncode == 0
    assert "Found 1 duplicate roxygen" in res_pass.stdout


def test_diff_scoped_filtering(tmp_path, monkeypatch):
    file1 = tmp_path / "f1.R"
    file1.write_text(
        """
#' Func 1
#' @param x A numeric vector of observation values to compute metrics over.
f1 <- function(x) x
""",
        encoding="utf-8",
    )
    file2 = tmp_path / "f2.R"
    file2.write_text(
        """
#' Func 2
#' @param x A numeric vector of observation values to compute metrics over.
f2 <- function(x) x
""",
        encoding="utf-8",
    )

    # If neither file is in diff_modified -> 0 duplicates reported
    monkeypatch.setattr(mod, "get_diff_modified_files", lambda ref, root: set())
    dups_none = mod.find_duplicate_roxygen(tmp_path, {".R"}, [], base_ref="origin/main")
    assert len(dups_none) == 0

    # If f2.R is modified -> 1 duplicate reported
    monkeypatch.setattr(mod, "get_diff_modified_files", lambda ref, root: {file2.resolve()})
    dups_one = mod.find_duplicate_roxygen(tmp_path, {".R"}, [], base_ref="origin/main")
    assert len(dups_one) == 1
