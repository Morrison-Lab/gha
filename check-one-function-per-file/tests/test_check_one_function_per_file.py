import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

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


def test_r_nested_functions_not_counted(tmp_path):
    nested_r = tmp_path / "nested.R"
    code = """
outer_func <- function(data) {
  inner_helper <- function(val) {
    val * 2
  }
  inner_helper(data)
}
"""
    nested_r.write_text(code, encoding="utf-8")
    violations = check_mod.check_repository(tmp_path, {".R"}, [])
    assert len(violations) == 0


def test_shell_functions(tmp_path):
    single_sh = tmp_path / "single.sh"
    single_sh.write_text("#!/bin/bash\nrun_task() {\n  echo 'hello'\n}\n", encoding="utf-8")

    multi_sh = tmp_path / "multi.sh"
    multi_sh.write_text("#!/bin/bash\nfunction task1 {\n  echo 1\n}\ntask2() {\n  echo 2\n}\n", encoding="utf-8")

    violations = check_mod.check_repository(tmp_path, {".sh"}, [])
    assert single_sh not in violations
    assert multi_sh in violations
    assert len(violations[multi_sh]) == 2


def test_js_ts_functions(tmp_path):
    single_js = tmp_path / "single.js"
    single_js.write_text("export function processItem(item) {\n  return item;\n}\n", encoding="utf-8")

    multi_ts = tmp_path / "multi.ts"
    multi_ts.write_text("export const f1 = (a: number) => a + 1;\nexport const f2 = function(b: number) { return b; };\n", encoding="utf-8")

    violations = check_mod.check_repository(tmp_path, {".js", ".ts"}, [])
    assert single_js not in violations
    assert multi_ts in violations
    assert len(violations[multi_ts]) == 2


def test_julia_functions(tmp_path):
    single_jl = tmp_path / "single.jl"
    single_jl.write_text("function compute(x)\n  x^2\nend\n", encoding="utf-8")

    multi_jl = tmp_path / "multi.jl"
    multi_jl.write_text("function f1(x)\n  x\nend\n\nf2(y) = y * 2\n", encoding="utf-8")

    violations = check_mod.check_repository(tmp_path, {".jl"}, [])
    assert single_jl not in violations
    assert multi_jl in violations
    assert len(violations[multi_jl]) == 2


def test_opt_out_comments(tmp_path):
    # Test built-in opt-out comment styles
    opt_out_1 = tmp_path / "opt1.py"
    opt_out_1.write_text("# check-one-function-per-file: allow-multiple\ndef a(): pass\ndef b(): pass\n", encoding="utf-8")

    opt_out_2 = tmp_path / "opt2.R"
    opt_out_2.write_text("# allow-multiple-functions\nfn1 <- function() {}\nfn2 <- function() {}\n", encoding="utf-8")

    opt_out_3 = tmp_path / "opt3.js"
    opt_out_3.write_text("// check-one-function-per-file: opt-out\nfunction a() {}\nfunction b() {}\n", encoding="utf-8")

    violations = check_mod.check_repository(tmp_path, {".py", ".R", ".js"}, [])
    assert len(violations) == 0


def test_custom_opt_out_comment(tmp_path):
    custom_opt = tmp_path / "custom.py"
    custom_opt.write_text("# NO_ONE_FUNC_CHECK\ndef f1(): pass\ndef f2(): pass\n", encoding="utf-8")

    violations_without_flag = check_mod.check_repository(tmp_path, {".py"}, [])
    assert custom_opt in violations_without_flag

    violations_with_flag = check_mod.check_repository(tmp_path, {".py"}, [], custom_opt_out="# NO_ONE_FUNC_CHECK")
    assert len(violations_with_flag) == 0


def test_paths_ignore(tmp_path):
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    test_file = test_dir / "test_something.py"
    test_file.write_text("def test_a(): pass\ndef test_b(): pass\n", encoding="utf-8")

    violations = check_mod.check_repository(tmp_path, {".py"}, ["tests"])
    assert len(violations) == 0


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
    # Test fail: true (default)
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

    # Test fail: false (warning mode)
    res_warn = subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={**os.environ, "INPUT_PATH": str(tmp_path), "INPUT_FAIL": "false"},
    )
    assert res_warn.returncode == 0
    assert "::error" in res_warn.stdout
