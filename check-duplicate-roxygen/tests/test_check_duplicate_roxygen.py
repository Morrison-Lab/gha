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


def test_comma_separated_params(tmp_path):
    r_file = tmp_path / "multi_param.R"
    r_file.write_text(
        """
#' Calculate distance
#' @param x,y Numeric coordinates of data points.
calc_dist <- function(x, y) sqrt(x^2 + y^2)

#' Another distance
#' @param x Numeric coordinates of data points.
other_dist <- function(x) x
""",
        encoding="utf-8",
    )
    duplicates = mod.find_duplicate_roxygen(tmp_path, {".R"}, [])
    assert len(duplicates) == 1
    assert duplicates[0].param_name == "x"
    assert len(duplicates[0].occurrences) == 2


def test_multiline_signature_with_default_parens(tmp_path):
    r_file = tmp_path / "complex_args.R"
    r_file.write_text(
        """
#' Complex function
#' @param alpha First parameter description.
#' @param beta Second parameter description.
#' @param gamma Third parameter description.
complex_fn <- function(
    alpha = c("first", "second"),
    beta = getOption("my_option", default = 42),
    gamma = 100
) {
    list(alpha, beta, gamma)
}
""",
        encoding="utf-8",
    )
    blocks = mod.parse_roxygen_blocks(r_file, r_file.read_text(encoding="utf-8"))
    assert len(blocks) == 1
    assert blocks[0].func_name == "complex_fn"
    assert blocks[0].func_args == ["alpha", "beta", "gamma"]


def test_indented_function(tmp_path):
    r_file = tmp_path / "indented.R"
    r_file.write_text(
        """
    #' Indented function
    #' @param x Parameter x description.
    indented_fn <- function(x) {
        x + 1
    }
""",
        encoding="utf-8",
    )
    blocks = mod.parse_roxygen_blocks(r_file, r_file.read_text(encoding="utf-8"))
    assert len(blocks) == 1
    assert blocks[0].func_name == "indented_fn"
    assert blocks[0].func_args == ["x"]


def test_param_opt_out_does_not_leak_to_block(tmp_path):
    r_file = tmp_path / "leak.R"
    r_file.write_text(
        """
#' First function
#' @param a Common documentation for param a. # check-duplicate-roxygen: allow-duplicates
#' @param b Common documentation for param b.
fn_one <- function(a, b) a + b

#' Second function
#' @param a Common documentation for param a.
#' @param b Common documentation for param b.
fn_two <- function(a, b) a + b
""",
        encoding="utf-8",
    )
    duplicates = mod.find_duplicate_roxygen(tmp_path, {".R"}, [])
    # 'a' is opted out in fn_one, so only 'b' should be flagged as duplicate
    assert len(duplicates) == 1
    assert duplicates[0].param_name == "b"


def test_in_block_opt_out_in_first_20_lines_does_not_leak_to_file(tmp_path):
    r_file = tmp_path / "top_block.R"
    r_file.write_text(
        """#' Early function with block opt-out
#' check-duplicate-roxygen: allow-duplicates
#' @param x Duplicate description for x.
early_fn <- function(x) x

#' Late function without opt-out
#' @param y Duplicate description for y.
late_fn <- function(y) y

#' Partner function
#' @param y Duplicate description for y.
partner_fn <- function(y) y
""",
        encoding="utf-8",
    )
    duplicates = mod.find_duplicate_roxygen(tmp_path, {".R"}, [])
    # 'x' is in the opted out block, but 'y' is in non-opted-out blocks and must be flagged
    assert len(duplicates) == 1
    assert duplicates[0].param_name == "y"


def test_diff_scoped_priority_prefers_unmodified_base(tmp_path, monkeypatch):
    base_file = tmp_path / "z_base.R"
    base_file.write_text(
        """
#' Base canonical function
#' @param val A numeric vector of predictor values.
calc_base <- function(val) val
""",
        encoding="utf-8",
    )
    pr_file = tmp_path / "a_pr.R"
    pr_file.write_text(
        """
#' PR new function
#' @param val A numeric vector of predictor values.
calc_pr <- function(val) val
""",
        encoding="utf-8",
    )

    # pr_file is modified in PR, base_file is untouched base code
    monkeypatch.setattr(mod, "get_diff_modified_files", lambda ref, root: {pr_file.resolve()})
    duplicates = mod.find_duplicate_roxygen(tmp_path, {".R"}, [], base_ref="origin/main")
    assert len(duplicates) == 1
    group = duplicates[0]
    # Canonical primary block must be calc_base from the untouched base file!
    assert group.primary_block.func_name == "calc_base"
    # Recommendation must tell calc_pr to inherit from calc_base
    assert any("calc_pr" in r and "@inheritParams calc_base" in r for r in group.recommendations)


def test_intra_block_duplicate_param(tmp_path):
    r_file = tmp_path / "intra.R"
    r_file.write_text(
        """
#' Function with duplicate param inside block
#' @param x A numeric vector of predictor values.
#' @param x A numeric vector of predictor values.
fn_intra <- function(x) x
""",
        encoding="utf-8",
    )
    duplicates = mod.find_duplicate_roxygen(tmp_path, {".R"}, [])
    assert len(duplicates) == 1
    group = duplicates[0]
    assert len(group.occurrences) == 2
    assert any("multiple times within the same function block" in r for r in group.recommendations)


def test_namespaced_inherit_params(tmp_path):
    r_file = tmp_path / "pkg_inherit.R"
    r_file.write_text(
        """
#' Base function
#' @param alpha Parameter alpha documentation.
base_fn <- function(alpha) alpha

#' Target function with namespaced inheritParams
#' @inheritParams mypkg::base_fn
#' @param alpha Parameter alpha documentation.
target_fn <- function(alpha) alpha
""",
        encoding="utf-8",
    )
    duplicates = mod.find_duplicate_roxygen(tmp_path, {".R"}, [])
    assert len(duplicates) == 1
    group = duplicates[0]
    assert any("Remove redundant '@param alpha'" in r for r in group.recommendations)


def test_defaults_agreement():
    import yaml

    repo_root = Path(__file__).resolve().parent.parent.parent
    action_yml = repo_root / "check-duplicate-roxygen" / "action.yml"
    workflow_yml = repo_root / ".github" / "workflows" / "check-duplicate-roxygen.yml"

    action_data = yaml.safe_load(action_yml.read_text(encoding="utf-8"))
    workflow_data = yaml.safe_load(workflow_yml.read_text(encoding="utf-8"))

    action_inputs = action_data["inputs"]
    on_clause = workflow_data.get("on") or workflow_data.get(True)
    workflow_inputs = on_clause["workflow_call"]["inputs"]

    shared_keys = {"path", "paths-ignore", "extensions", "min-desc-length", "base-ref", "fail", "python-version"}
    assert shared_keys.issubset(set(action_inputs.keys()))
    assert shared_keys.issubset(set(workflow_inputs.keys()))

    for key in ("path", "paths-ignore", "extensions", "min-desc-length", "base-ref", "python-version"):
        assert str(action_inputs[key]["default"]) == str(workflow_inputs[key]["default"])

    assert str(action_inputs["fail"]["default"]).lower() in ("true", "1")
    assert str(workflow_inputs["fail"]["default"]).lower() in ("true", "1")

    assert mod.DEFAULT_MIN_DESC_LENGTH == int(action_inputs["min-desc-length"]["default"])
    expected_exts = {e.strip() for e in action_inputs["extensions"]["default"].split(",") if e.strip()}
    assert mod.DEFAULT_EXTENSIONS == expected_exts
    expected_ignore = [p.strip() for p in action_inputs["paths-ignore"]["default"].split(",") if p.strip()]
    assert mod.DEFAULT_PATHS_IGNORE == expected_ignore


def test_param_redos_resilience():
    # Verify that comma-separated parameter parsing has no polynomial/exponential backtracking
    attack_line = "#' @param " + ".,...," * 200 + "x final_desc"
    res = mod.parse_param_line(attack_line)
    assert res is not None
    names, desc = res
    assert len(names) == 401
    assert desc == "final_desc"
