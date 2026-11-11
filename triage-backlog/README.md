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
The files it cites, `shared/workflow/triage-backlog.md` and `skills/triage/SKILL.md`, are in `Morrison-Lab/ai-config`.

Run the tests with `python3 triage-backlog/tests/test_triage_backlog.py`.
