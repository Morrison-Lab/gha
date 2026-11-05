- **`student-qmd` keeps blank-line runs inside code fences.**
  The generator collapsed every run of blank lines, so Python with two blank
  lines between definitions (PEP 8) came out changed and the check failed on
  it ([gha#1173](https://github.com/Morrison-Lab/gha/issues/1173)).
