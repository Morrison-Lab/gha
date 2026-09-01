import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

# Import module under test
sys.path.insert(0, str(Path(__file__).parent.parent))
import importlib
check_mod = importlib.import_module("check-one-function-per-file")


def test_python_single_function(tmp_path):
    py_file = tmp_path / "single.py"
    py_file.write_text("def my_func():\n    return 42\n", encoding="utf-8")
    violations = check_mod.check_repository(tmp_path, {".py"}, [])
    assert len(violations) == 0


def test_python_multiple_functions(tmp_path):
    py_file = tmp_path / "multiple.py"
    py_file.write_text("def func1():\n    pass\n\ndef func2():\n    pass\n", encoding="utf-8")
    violations = check_mod.check_repository(tmp_path, {".py"}, [])
    assert py_file in violations
    assert len(violations[py_file]) == 2
    assert violations[py_file][0][0] == "func1"
    assert violations[py_file][1][0] == "func2"


def test_python_class_methods_and_nested_functions(tmp_path):
    py_file = tmp_path / "class_and_nested.py"
    code = """
class MyClass:
    def method1(self):
        pass
    def method2(self):
        pass

def standalone():
    def inner_helper():
        pass
    return inner_helper()
"""
    py_file.write_text(code, encoding="utf-8")
    violations = check_mod.check_repository(tmp_path, {".py"}, [])
    # Only 1 top-level function 'standalone'; methods in classes and inner helpers are ignored
    assert len(violations) == 0


def test_r_single_and_multiple_functions(tmp_path):
    single_r = tmp_path / "single.R"
    single_r.write_text("calculate_metric <- function(x) {\n  x + 1\n}\n", encoding="utf-8")

    multi_r = tmp_path / "multi.R"
    multi_r.write_text("fn1 <- function(x) x\nfn2 = function(y) y\n", encoding="utf-8")

    violations = check_mod.check_repository(tmp_path, {".R", ".r"}, [])
    assert single_r not in violations
    assert multi_r in violations
    assert len(violations[multi_r]) == 2
    assert violations[multi_r][0][0] == "fn1"
    assert violations[multi_r][1][0] == "fn2"


def test_r_backtick_quoted_function_names(tmp_path):
    # Operators and special S3 method names in backticks
    op_r = tmp_path / "op.R"
    op_r.write_text("`%+%` <- function(a, b) {\n  paste0(a, b)\n}\n", encoding="utf-8")

    s3_r = tmp_path / "s3.R"
    s3_r.write_text("`[.myclass` <- function(x, i) {\n  x[i]\n}\n", encoding="utf-8")

    violations = check_mod.check_repository(tmp_path, {".R"}, [])
    assert op_r not in violations
    assert s3_r not in violations


def test_r_shorthand_lambda_syntax(tmp_path):
    # R 4.1+ \(x) shorthand syntax
    shorthand_r = tmp_path / "shorthand.R"
    shorthand_r.write_text("f1 <- \\(x) x + 1\nf2 <- \\(y) { y * 2 }\n", encoding="utf-8")

    violations = check_mod.check_repository(tmp_path, {".R"}, [])
    assert shorthand_r in violations
    assert len(violations[shorthand_r]) == 2


def test_r_named_function_arguments_inside_calls_not_flagged(tmp_path):
    # e.g. purrr::map(.f = function(y) ...) should not be detected as top-level function definition
    code = """
run_pipeline <- function(data) {
  result <- purrr::map(
    data,
    .f = function(y) {
      y * 2
    }
  )
  result
}
"""
    r_file = tmp_path / "pipeline.R"
    r_file.write_text(code, encoding="utf-8")
    violations = check_mod.check_repository(tmp_path, {".R"}, [])
    assert len(violations) == 0


def test_shell_functions_and_array_expansions(tmp_path):
    single_sh = tmp_path / "single.sh"
    code = """#!/bin/bash
run_task() {
  len="${#MY_VAR}"
  arr_len=${#my_arr[@]}
  echo "Length: ${len}, Arr: ${arr_len}"
}

second_task() {
  echo "Second task"
}
"""
    single_sh.write_text(code, encoding="utf-8")

    violations = check_mod.check_repository(tmp_path, {".sh"}, [])
    assert single_sh in violations
    assert len(violations[single_sh]) == 2
    assert violations[single_sh][0][0] == "run_task"
    assert violations[single_sh][1][0] == "second_task"


def test_js_ts_block_comments_and_generics(tmp_path):
    single_js = tmp_path / "single.js"
    code = """
/**
 * JSDoc comment with code block:
 * function example() {
 *   return 1;
 * }
 */
export function processItem(item) {
  const url = 'https://example.com//test';
  return item;
}
"""
    single_js.write_text(code, encoding="utf-8")

    multi_ts = tmp_path / "multi.ts"
    multi_ts.write_text("export const f1 = <T>(a: T): T => a;\nexport const f2: Handler = function(b) { return b; };\n", encoding="utf-8")

    violations = check_mod.check_repository(tmp_path, {".js", ".ts"}, [])
    assert single_js not in violations
    assert multi_ts in violations
    assert len(violations[multi_ts]) == 2


def test_js_ts_block_comments_preserve_line_numbers(tmp_path):
    js_file = tmp_path / "comments_and_lines.js"
    code = """/**
 * Example block comment
 * line 3
 * line 4
 */
function first() {
  return 1;
}

function second() {
  return 2;
}
"""
    js_file.write_text(code, encoding="utf-8")
    violations = check_mod.check_repository(tmp_path, {".js"}, [])
    assert js_file in violations
    assert len(violations[js_file]) == 2
    assert violations[js_file][0] == ("first", 6)
    assert violations[js_file][1] == ("second", 10)


def test_opt_out_after_multiline_docstring(tmp_path):
    py_file = tmp_path / "multiline_doc.py"
    code = '''"""
Module docstring line 1.
Module docstring line 2.
"""
# check-one-function-per-file: allow-multiple

def f1():
    pass

def f2():
    pass
'''
    py_file.write_text(code, encoding="utf-8")
    violations = check_mod.check_repository(tmp_path, {".py"}, [])
    assert len(violations) == 0


def test_opt_out_with_shebang_and_multiline_docstring(tmp_path):
    py_file = tmp_path / "shebang_doc.py"
    code = '''#!/usr/bin/env python3
"""
Module docstring line 1.
Module docstring line 2.
"""
# check-one-function-per-file: allow-multiple

def f1():
    pass

def f2():
    pass
'''
    py_file.write_text(code, encoding="utf-8")
    violations = check_mod.check_repository(tmp_path, {".py"}, [])
    assert len(violations) == 0


def test_opt_out_after_long_docstring(tmp_path):
    py_file = tmp_path / "long_doc.py"
    doc_lines = "\n".join(f"Doc line {i}" for i in range(70))
    code = f'''"""\n{doc_lines}\n"""\n# check-one-function-per-file: allow-multiple\n\ndef f1(): pass\ndef f2(): pass\n'''
    py_file.write_text(code, encoding="utf-8")
    violations = check_mod.check_repository(tmp_path, {".py"}, [])
    assert len(violations) == 0


def test_julia_multiple_dispatch_deduplicated(tmp_path):
    single_jl = tmp_path / "dispatch.jl"
    single_jl.write_text("compute(x::Int) = x + 1\ncompute(x::String) = x * '!'\n", encoding="utf-8")

    multi_jl = tmp_path / "multi.jl"
    multi_jl.write_text("function f1(x)\n  x\nend\n\nf2(y) = y * 2\n", encoding="utf-8")

    violations = check_mod.check_repository(tmp_path, {".jl"}, [])
    assert single_jl not in violations
    assert multi_jl in violations
    assert len(violations[multi_jl]) == 2


def test_opt_out_comments(tmp_path):
    opt_out_1 = tmp_path / "opt1.py"
    opt_out_1.write_text("# check-one-function-per-file: allow-multiple\ndef a(): pass\ndef b(): pass\n", encoding="utf-8")

    opt_out_2 = tmp_path / "opt2.R"
    opt_out_2.write_text("# allow-multiple-functions\nfn1 <- function() {}\nfn2 <- function() {}\n", encoding="utf-8")

    opt_out_3 = tmp_path / "opt3.js"
    opt_out_3.write_text("// check-one-function-per-file: opt-out\nfunction a() {}\nfunction b() {}\n", encoding="utf-8")

    violations = check_mod.check_repository(tmp_path, {".py", ".R", ".js"}, [])
    assert len(violations) == 0


def test_opt_out_comment_not_triggered_by_body_string(tmp_path):
    # A string deep in the file body quoting opt-out directive should not self-exempt
    f = tmp_path / "no_self_exempt.py"
    code = '''"""Module docstring."""

def f1():
    pass

def f2():
    msg = "# check-one-function-per-file: allow-multiple"
    return msg
'''
    f.write_text(code, encoding="utf-8")
    violations = check_mod.check_repository(tmp_path, {".py"}, [])
    assert f in violations
    assert len(violations[f]) == 2


def test_custom_opt_out_comment(tmp_path):
    custom_opt = tmp_path / "custom.py"
    custom_opt.write_text("# NO_ONE_FUNC_CHECK\ndef f1(): pass\ndef f2(): pass\n", encoding="utf-8")

    violations_without_flag = check_mod.check_repository(tmp_path, {".py"}, [])
    assert custom_opt in violations_without_flag

    violations_with_flag = check_mod.check_repository(tmp_path, {".py"}, [], custom_opt_out="# NO_ONE_FUNC_CHECK")
    assert len(violations_with_flag) == 0


def test_paths_ignore_does_not_falsely_ignore_substrings(tmp_path):
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    test_file = test_dir / "test_something.py"
    test_file.write_text("def test_a(): pass\ndef test_b(): pass\n", encoding="utf-8")

    contests_file = tmp_path / "contests.py"
    contests_file.write_text("def c1(): pass\ndef c2(): pass\n", encoding="utf-8")

    violations = check_mod.check_repository(tmp_path, {".py"}, ["tests", "test"])
    assert test_file not in violations
    assert contests_file in violations


def test_defaults_agreement_across_action_workflow_and_script():
    """Assert action.yml, check-one-function-per-file.yml, and script defaults agree (gha#303 precedent)."""
    repo_root = Path(__file__).resolve().parents[2]
    action_yml_path = repo_root / "check-one-function-per-file" / "action.yml"
    workflow_yml_path = repo_root / ".github" / "workflows" / "check-one-function-per-file.yml"

    action_spec = yaml.safe_load(action_yml_path.read_text(encoding="utf-8"))
    workflow_spec = yaml.safe_load(workflow_yml_path.read_text(encoding="utf-8"))

    action_inputs = action_spec["inputs"]
    on_block = workflow_spec.get("on") or workflow_spec.get(True)
    workflow_inputs = on_block["workflow_call"]["inputs"]

    # Check extensions
    action_exts = check_mod.parse_extensions(action_inputs["extensions"]["default"])
    workflow_exts = check_mod.parse_extensions(workflow_inputs["extensions"]["default"])
    script_exts = check_mod.DEFAULT_EXTENSIONS
    assert action_exts == script_exts, f"action.yml extensions default mismatch: {action_exts} vs {script_exts}"
    assert workflow_exts == script_exts, f"workflow extensions default mismatch: {workflow_exts} vs {script_exts}"

    # Check paths-ignore
    action_ignores = check_mod.parse_paths_ignore(action_inputs["paths-ignore"]["default"])
    workflow_ignores = check_mod.parse_paths_ignore(workflow_inputs["paths-ignore"]["default"])
    script_ignores = check_mod.DEFAULT_PATHS_IGNORE
    assert set(action_ignores) == set(script_ignores)
    assert set(workflow_ignores) == set(script_ignores)


def test_cli_execution_clean(tmp_path):
    f = tmp_path / "good.py"
    f.write_text("def single(): pass\n", encoding="utf-8")

    script = Path(check_mod.__file__).resolve()
    res = subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={**os.environ, "INPUT_PATH": str(tmp_path)},
    )
    assert res.returncode == 0
    assert "✅ No one-function-per-file violations found." in res.stdout


def test_cli_execution_violations(tmp_path):
    f = tmp_path / "bad.py"
    f.write_text("def f1(): pass\ndef f2(): pass\n", encoding="utf-8")

    script = Path(check_mod.__file__).resolve()
    res_fail = subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={**os.environ, "INPUT_PATH": str(tmp_path), "INPUT_FAIL": "true"},
    )
    assert res_fail.returncode == 1
    assert "::error" in res_fail.stdout
    assert "bad.py" in res_fail.stdout

    res_warn = subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={**os.environ, "INPUT_PATH": str(tmp_path), "INPUT_FAIL": "false"},
    )
    assert res_warn.returncode == 0
    assert "::warning" in res_warn.stdout
    assert "::error" not in res_warn.stdout
