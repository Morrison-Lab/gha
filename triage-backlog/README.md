# triage-backlog

`triage-backlog.py` is a copy of `scripts/triage-backlog.py` from
[`Morrison-Lab/ai-config`](https://github.com/Morrison-Lab/ai-config),
taken at commit `a70fbf68d2f147b53728077124480c15943dafeb` (gha#1900).
The copy differs from the source in one line:
the `check-one-function-per-file: allow-multiple` comment on line 2.

`tests/test_triage_backlog.py` is a copy of `scripts/test_triage_backlog.py` at the same commit.
It differs in the two lines that locate the script, which now sits one directory up.

The script's docstring keeps the source's wording.
Its usage lines say `scripts/triage-backlog.py`; here the path is `triage-backlog/triage-backlog.py`.
It also cites `shared/workflow/triage-backlog.md` and `skills/triage/SKILL.md`, which are files in `Morrison-Lab/ai-config`.

Run the tests with `python3 triage-backlog/tests/test_triage_backlog.py`.

## The composite action

`action.yml` runs the script with `--apply --labels-only`.
It labels each open issue that has no priority label, and closes nothing.

| Input | Default | Meaning |
| --- | --- | --- |
| `repo` | the calling repository | The repository to triage, as `owner/name`. |
| `dry-run` | `false` | Print each label command without running it. Only an explicit `false` changes labels. |
| `ceiling` | empty | The open-issue count to report against. A run over it passes with a warning. |
| `github-token` | `github.token` | The token `gh` uses. |

The job needs `issues: write`, or `issues: read` for a dry run.
The repository must already have the labels `P1`, `P2` and `P3`: the action checks for them before it changes anything.
The `triage-backlog-tests` job in `.github/workflows/_selftest.yml` calls the action three times, each as a dry run.
